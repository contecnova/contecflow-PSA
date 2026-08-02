"""
CMDB Discovery Orchestration — Cloud & Infrastructure Discovery
=================================================================
Funciones de descubrimiento de múltiples proveedores (AWS, K8s, vSphere, Azure, GCP, SNMP)
y orquestación de jobs de descubrimiento.
"""
import json
import logging
from datetime import timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session

from app.models.cmdb import CMDBDiscoveryJob, CMDBDiscoveryProvider
from app.services.cmdb.parser import load_config, snmp_get_interfaces
from app.services.cmdb.utils import (
    utcnow, PROVIDER_AWS, PROVIDER_K8S, PROVIDER_VSPHERE, PROVIDER_AZURE, PROVIDER_GCP, PROVIDER_SNMP
)
from app.services.cmdb.models import reconcile_cis

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# AWS DISCOVERY
# ═══════════════════════════════════════════════════════════════════════════════

def discover_aws(provider_config: dict[str, Any]) -> list[dict[str, Any]]:
    """Descubre activos EC2 + RDS en AWS.

    Args:
        provider_config: Configuración con region_name, aws_access_key_id, aws_secret_access_key

    Returns:
        Lista de diccionarios con atributos de instancias descubiertas
    """
    try:
        import boto3  # noqa: PLC0415
    except ImportError as exc:
        raise ImportError(
            "El proveedor AWS requiere boto3. Instálalo con: pip install boto3"
        ) from exc

    region = provider_config.get("region_name", "us-east-1")
    session_kwargs: dict[str, Any] = {"region_name": region}
    if provider_config.get("aws_access_key_id"):
        session_kwargs["aws_access_key_id"] = provider_config["aws_access_key_id"]
        session_kwargs["aws_secret_access_key"] = provider_config.get("aws_secret_access_key", "")

    boto_session = boto3.Session(**session_kwargs)
    discovered: list[dict] = []

    # EC2 instances
    try:
        ec2 = boto_session.resource("ec2")
        for instance in ec2.instances.all():
            name_tag = next(
                (t["Value"] for t in (instance.tags or []) if t["Key"] == "Name"),
                instance.id,
            )
            discovered.append({
                "external_id": instance.id,
                "name": name_tag,
                "ci_type": "server",
                "status": "active" if instance.state["Name"] == "running" else "maintenance",
                "environment": next(
                    (t["Value"] for t in (instance.tags or []) if t["Key"].lower() in ("env", "environment")),
                    "production",
                ),
                "ip_address": instance.private_ip_address or "",
                "hostname": instance.public_dns_name or instance.id,
                "version": instance.instance_type,
                "description": f"AWS EC2 {instance.instance_type} — {instance.state['Name']}",
                "attributes": json.dumps({
                    "instance_type": instance.instance_type,
                    "ami": instance.image_id,
                    "az": instance.placement.get("AvailabilityZone", ""),
                    "vpc_id": instance.vpc_id or "",
                }),
                "discovery_provider": PROVIDER_AWS,
                "last_discovered_at": utcnow().isoformat(),
            })
    except Exception as exc:  # noqa: BLE001
        logger.warning("AWS EC2 discovery error: %s", exc)

    # RDS instances
    try:
        rds_client = boto_session.client("rds")
        paginator = rds_client.get_paginator("describe_db_instances")
        for page in paginator.paginate():
            for db in page.get("DBInstances", []):
                discovered.append({
                    "external_id": db["DBInstanceIdentifier"],
                    "name": db["DBInstanceIdentifier"],
                    "ci_type": "database",
                    "status": "active" if db["DBInstanceStatus"] == "available" else "maintenance",
                    "environment": "production",
                    "ip_address": db.get("Endpoint", {}).get("Address", ""),
                    "hostname": db.get("Endpoint", {}).get("Address", ""),
                    "version": f"{db.get('Engine', '')} {db.get('EngineVersion', '')}",
                    "description": f"AWS RDS {db.get('Engine', '')} — {db['DBInstanceStatus']}",
                    "attributes": json.dumps({
                        "engine": db.get("Engine", ""),
                        "engine_version": db.get("EngineVersion", ""),
                        "instance_class": db.get("DBInstanceClass", ""),
                        "multi_az": db.get("MultiAZ", False),
                    }),
                    "discovery_provider": PROVIDER_AWS,
                    "last_discovered_at": utcnow().isoformat(),
                })
    except Exception as exc:  # noqa: BLE001
        logger.warning("AWS RDS discovery error: %s", exc)

    logger.info("AWS discovery: %d activos encontrados", len(discovered))
    return discovered


# ═══════════════════════════════════════════════════════════════════════════════
# KUBERNETES DISCOVERY
# ═══════════════════════════════════════════════════════════════════════════════

def discover_kubernetes(provider_config: dict[str, Any]) -> list[dict[str, Any]]:
    """Descubre nodos y namespaces de un cluster Kubernetes."""
    try:
        from kubernetes import client as k8s_client  # noqa: PLC0415
        from kubernetes import config as k8s_config  # noqa: PLC0415
    except ImportError as exc:
        raise ImportError(
            "El proveedor Kubernetes requiere: pip install kubernetes"
        ) from exc

    try:
        if provider_config.get("in_cluster"):
            k8s_config.load_incluster_config()
        elif provider_config.get("kubeconfig_path"):
            k8s_config.load_kube_config(config_file=provider_config["kubeconfig_path"])
        else:
            k8s_config.load_kube_config()
    # intentional: chained re-raise preserves context
    except Exception as exc:
        raise RuntimeError(f"No se pudo cargar kubeconfig: {exc}") from exc

    v1 = k8s_client.CoreV1Api()
    discovered: list[dict] = []

    # Nodes
    try:
        for node in v1.list_node().items:
            meta = node.metadata
            status_obj = node.status
            conditions = {c.type: c.status for c in (status_obj.conditions or [])}
            is_ready = conditions.get("Ready") == "True"

            internal_ip = ""
            for addr in (status_obj.addresses or []):
                if addr.type == "InternalIP":
                    internal_ip = addr.address
                    break

            node_info = status_obj.node_info
            discovered.append({
                "external_id": meta.uid,
                "name": meta.name,
                "ci_type": "server",
                "status": "active" if is_ready else "maintenance",
                "environment": (meta.labels or {}).get("environment", "production") if meta.labels else "production",
                "ip_address": internal_ip,
                "hostname": meta.name,
                "version": node_info.kubelet_version if node_info else "",
                "description": f"K8s Node — kubelet {getattr(node_info, 'kubelet_version', '')}",
                "attributes": json.dumps({
                    "os": getattr(node_info, "os_image", ""),
                    "arch": getattr(node_info, "architecture", ""),
                    "container_runtime": getattr(node_info, "container_runtime_version", ""),
                    "labels": meta.labels or {},
                }),
                "discovery_provider": PROVIDER_K8S,
                "last_discovered_at": utcnow().isoformat(),
            })
    except Exception as exc:  # noqa: BLE001
        logger.warning("K8s nodes discovery error: %s", exc)

    # Namespaces
    try:
        for ns in v1.list_namespace().items:
            meta = ns.metadata
            phase = ns.status.phase if ns.status else "Active"
            discovered.append({
                "external_id": f"ns:{meta.uid}",
                "name": f"k8s-ns-{meta.name}",
                "ci_type": "service",
                "status": "active" if phase == "Active" else "decommissioned",
                "environment": (meta.labels or {}).get("environment", "production"),
                "ip_address": "",
                "hostname": "",
                "version": "",
                "description": f"Kubernetes Namespace: {meta.name}",
                "attributes": json.dumps({"namespace": meta.name, "labels": meta.labels or {}}),
                "discovery_provider": PROVIDER_K8S,
                "last_discovered_at": utcnow().isoformat(),
            })
    except Exception as exc:  # noqa: BLE001
        logger.warning("K8s namespaces discovery error: %s", exc)

    logger.info("K8s discovery: %d activos encontrados", len(discovered))
    return discovered


# ═══════════════════════════════════════════════════════════════════════════════
# VSPHERE DISCOVERY
# ═══════════════════════════════════════════════════════════════════════════════

def discover_vsphere(provider_config: dict[str, Any]) -> list[dict[str, Any]]:
    """Descubre VMs y hosts ESXi de vSphere/vCenter."""
    host = provider_config.get("host", "")
    user = provider_config.get("user", "")
    password = provider_config.get("password", "")
    port = int(provider_config.get("port", 443))
    disable_ssl = provider_config.get("disable_ssl_verification", False)

    discovered: list[dict] = []

    try:
        from pyVim.connect import SmartConnect, Disconnect  # noqa: PLC0415
        from pyVmomi import vim  # noqa: PLC0415
        import ssl  # noqa: PLC0415

        ssl_ctx = ssl.create_default_context()
        if disable_ssl:
            ssl_ctx.check_hostname = False
            ssl_ctx.verify_mode = ssl.CERT_NONE

        si = SmartConnect(host=host, user=user, pwd=password, port=port, sslContext=ssl_ctx)
        content = si.RetrieveContent()
        container = content.viewManager.CreateContainerView(
            content.rootFolder, [vim.VirtualMachine, vim.HostSystem], True
        )

        for obj in container.view:
            if isinstance(obj, vim.VirtualMachine):
                cfg = obj.config
                if not cfg:
                    continue
                runtime = obj.runtime
                guest = obj.guest
                ip = getattr(guest, "ipAddress", "") or ""
                hostname = getattr(guest, "hostName", cfg.name) or cfg.name
                power = getattr(runtime, "powerState", "poweredOff")

                discovered.append({
                    "external_id": cfg.instanceUuid or cfg.name,
                    "name": cfg.name,
                    "ci_type": "virtual_machine",
                    "status": "active" if power == "poweredOn" else "maintenance",
                    "environment": "production",
                    "ip_address": ip,
                    "hostname": hostname,
                    "version": getattr(cfg, "guestFullName", "") or "",
                    "description": f"VMware VM — {power}",
                    "attributes": json.dumps({
                        "num_cpu": cfg.hardware.numCPU if cfg.hardware else 0,
                        "memory_mb": cfg.hardware.memoryMB if cfg.hardware else 0,
                        "guest_os": getattr(cfg, "guestFullName", ""),
                        "power_state": power,
                    }),
                    "discovery_provider": PROVIDER_VSPHERE,
                    "last_discovered_at": utcnow().isoformat(),
                })

            elif isinstance(obj, vim.HostSystem):
                runtime = obj.runtime
                hw = obj.hardware
                hostname = obj.name
                connection_state = getattr(runtime, "connectionState", "disconnected")

                discovered.append({
                    "external_id": obj._moId or hostname,  # noqa: SLF001
                    "name": hostname,
                    "ci_type": "server",
                    "status": "active" if connection_state == "connected" else "maintenance",
                    "environment": "production",
                    "ip_address": hostname,
                    "hostname": hostname,
                    "version": getattr(hw, "systemInfo", None) and hw.systemInfo.model or "",
                    "description": f"VMware ESXi Host — {connection_state}",
                    "attributes": json.dumps({
                        "vendor": hw.systemInfo.vendor if hw and hw.systemInfo else "",
                        "model": hw.systemInfo.model if hw and hw.systemInfo else "",
                        "cpu_model": hw.cpuInfo.hz if hw and hw.cpuInfo else 0,
                    }),
                    "discovery_provider": PROVIDER_VSPHERE,
                    "last_discovered_at": utcnow().isoformat(),
                })

        container.Destroy()
        Disconnect(si)

    except ImportError:
        logger.warning("pyVmomi no instalado — vSphere discovery no disponible")
    except Exception as exc:  # noqa: BLE001
        logger.error("vSphere discovery error: %s", exc)

    logger.info("vSphere discovery: %d activos encontrados", len(discovered))
    return discovered


# ═══════════════════════════════════════════════════════════════════════════════
# AZURE DISCOVERY
# ═══════════════════════════════════════════════════════════════════════════════

def discover_azure(provider_config: dict[str, Any]) -> list[dict[str, Any]]:
    """Descubre VMs y recursos de Azure Resource Manager."""
    subscription_id = provider_config.get("subscription_id", "")
    resource_group = provider_config.get("resource_group")
    tenant_id = provider_config.get("tenant_id")
    client_id_sp = provider_config.get("client_id")
    client_secret = provider_config.get("client_secret")

    discovered: list[dict] = []

    try:
        from azure.identity import ClientSecretCredential, DefaultAzureCredential  # noqa: PLC0415
        from azure.mgmt.compute import ComputeManagementClient  # noqa: PLC0415
    except ImportError as exc:
        raise ImportError(
            "Azure discovery requiere: pip install azure-mgmt-compute azure-identity"
        ) from exc

    try:
        if tenant_id and client_id_sp and client_secret:
            credential = ClientSecretCredential(
                tenant_id=tenant_id,
                client_id=client_id_sp,
                client_secret=client_secret,
            )
        else:
            credential = DefaultAzureCredential()

        compute_client = ComputeManagementClient(credential, subscription_id)

        vm_iter = (
            compute_client.virtual_machines.list_by_resource_group(resource_group)
            if resource_group
            else compute_client.virtual_machines.list_all()
        )
        for vm in vm_iter:
            vm_id = vm.id or vm.name
            power_state = "unknown"
            try:
                instance_view = compute_client.virtual_machines.instance_view(
                    vm.id.split("/")[4], vm.name,
                )
                for status in (instance_view.statuses or []):
                    if status.code and status.code.startswith("PowerState/"):
                        power_state = status.code.replace("PowerState/", "")
                        break
            except Exception:  # noqa: BLE001, S110
                pass

            discovered.append({
                "external_id": vm_id,
                "name": vm.name,
                "ci_type": "virtual_machine",
                "status": "active" if power_state == "running" else "maintenance",
                "environment": (vm.tags or {}).get("Environment", "production"),
                "ip_address": "",
                "hostname": vm.name,
                "version": vm.storage_profile.image_reference.sku if vm.storage_profile and vm.storage_profile.image_reference else "",
                "description": f"Azure VM — {vm.location} — {power_state}",
                "attributes": json.dumps({
                    "location": vm.location,
                    "vm_size": vm.hardware_profile.vm_size if vm.hardware_profile else "",
                    "os_type": str(vm.storage_profile.os_disk.os_type) if vm.storage_profile and vm.storage_profile.os_disk else "",
                    "power_state": power_state,
                    "resource_group": vm.id.split("/")[4] if vm.id else "",
                }),
                "discovery_provider": PROVIDER_AZURE,
                "last_discovered_at": utcnow().isoformat(),
            })
    except Exception as exc:  # noqa: BLE001
        logger.error("Azure discovery error: %s", exc)

    logger.info("Azure discovery: %d activos encontrados", len(discovered))
    return discovered


# ═══════════════════════════════════════════════════════════════════════════════
# GCP DISCOVERY
# ═══════════════════════════════════════════════════════════════════════════════

def discover_gcp(provider_config: dict) -> list[dict]:
    """Descubre activos de Google Cloud (Compute Engine VMs)."""
    project_id = (provider_config.get("project_id") or "").strip()
    if not project_id:
        raise ValueError("GCP discovery requiere project_id en provider config")

    discovered: list[dict] = []

    try:
        from google.cloud import compute_v1  # noqa: PLC0415
        from google.oauth2 import service_account  # noqa: PLC0415
    except ImportError as exc:
        raise ImportError(
            "GCP discovery requiere: pip install google-cloud-compute"
        ) from exc

    try:
        service_account_file = provider_config.get("service_account_file")
        if service_account_file:
            creds = service_account.Credentials.from_service_account_file(service_account_file)
            instances_client = compute_v1.InstancesClient(credentials=creds)
        else:
            instances_client = compute_v1.InstancesClient()

        for instance in instances_client.aggregated_list(project=project_id):
            scoped_list = instance[1]
            for vm in (scoped_list.instances or []):
                labels = dict(vm.labels or {})
                net_ifaces = list(vm.network_interfaces or [])
                nic0 = net_ifaces[0] if net_ifaces else None
                ip = nic0.network_i_p if nic0 else ""

                discovered.append({
                    "external_id": vm.id and str(vm.id) or vm.name,
                    "name": vm.name,
                    "ci_type": "virtual_machine",
                    "status": "active" if vm.status == "RUNNING" else "maintenance",
                    "environment": labels.get("environment", "production"),
                    "ip_address": ip,
                    "hostname": vm.name,
                    "version": vm.machine_type.split("/")[-1] if vm.machine_type else "",
                    "description": f"GCP Compute VM — {vm.zone.split('/')[-1] if vm.zone else ''} — {vm.status}",
                    "attributes": json.dumps({
                        "project_id": project_id,
                        "zone": vm.zone.split("/")[-1] if vm.zone else "",
                        "machine_type": vm.machine_type,
                        "labels": labels,
                        "disks": [d.source.split("/")[-1] for d in (vm.disks or []) if d.source],
                    }),
                    "discovery_provider": PROVIDER_GCP,
                    "last_discovered_at": utcnow().isoformat(),
                })
    except Exception as exc:  # noqa: BLE001
        logger.error("GCP discovery error: %s", exc)

    logger.info("GCP discovery: %d activos encontrados", len(discovered))
    return discovered


# ═══════════════════════════════════════════════════════════════════════════════
# SNMP DISCOVERY
# ═══════════════════════════════════════════════════════════════════════════════

def discover_snmp(provider_config: dict[str, Any]) -> list[dict[str, Any]]:
    """Descubre activos de red mediante SNMP v2c/v3."""
    try:
        from pysnmp.hlapi import (  # noqa: PLC0415
            CommunityData, ContextData, ObjectIdentity, ObjectType,
            SnmpEngine, UdpTransportTarget, getCmd,
        )
        from pysnmp.hlapi import UsmUserData, usmHMACSHAAuthProtocol, usmAesCfb128Protocol  # noqa: PLC0415
    except ImportError as exc:
        raise ImportError(
            "SNMP discovery requiere: pip install pysnmp"
        ) from exc

    import ipaddress  # noqa: PLC0415

    community = provider_config.get("community", "public")
    port = int(provider_config.get("port", 161))
    timeout = int(provider_config.get("timeout", 2))
    retries = int(provider_config.get("retries", 1))
    version = provider_config.get("version", "v2c")

    raw_hosts: list[str] = provider_config.get("hosts", [])

    host_ips: list[str] = []
    for h in raw_hosts:
        try:
            net = ipaddress.ip_network(h, strict=False)
            host_ips.extend(str(ip) for ip in list(net.hosts())[:1024])
        except ValueError:
            host_ips.append(h)

    discovered: list[dict] = []

    _OID_SYS_DESCR = "1.3.6.1.2.1.1.1.0"
    _OID_SYS_NAME  = "1.3.6.1.2.1.1.5.0"
    _OID_SYS_LOCATION = "1.3.6.1.2.1.1.6.0"
    _OID_SYS_CONTACT  = "1.3.6.1.2.1.1.4.0"
    _OID_SYS_OBJECTID = "1.3.6.1.2.1.1.2.0"

    def _auth_data():
        if version == "v3":
            return UsmUserData(
                provider_config.get("v3_user", "admin"),
                authKey=provider_config.get("v3_auth_key", ""),
                privKey=provider_config.get("v3_priv_key", ""),
                authProtocol=usmHMACSHAAuthProtocol,
                privProtocol=usmAesCfb128Protocol,
            )
        return CommunityData(community, mpModel=1)  # noqa: S508

    engine = SnmpEngine()

    for ip in host_ips:
        try:
            transport = UdpTransportTarget((ip, port), timeout=timeout, retries=retries)
            oids = [
                ObjectType(ObjectIdentity(_OID_SYS_DESCR)),
                ObjectType(ObjectIdentity(_OID_SYS_NAME)),
                ObjectType(ObjectIdentity(_OID_SYS_LOCATION)),
                ObjectType(ObjectIdentity(_OID_SYS_CONTACT)),
                ObjectType(ObjectIdentity(_OID_SYS_OBJECTID)),
            ]
            error_indication, error_status, _, var_binds = next(
                getCmd(engine, _auth_data(), transport, ContextData(), *oids)
            )

            if error_indication or error_status:
                continue

            values: dict[str, str] = {}
            for var_bind in var_binds:
                oid_str = str(var_bind[0])
                val_str = str(var_bind[1])
                if _OID_SYS_DESCR in oid_str:
                    values["sys_descr"] = val_str
                elif _OID_SYS_NAME in oid_str:
                    values["sys_name"] = val_str
                elif _OID_SYS_LOCATION in oid_str:
                    values["sys_location"] = val_str
                elif _OID_SYS_CONTACT in oid_str:
                    values["sys_contact"] = val_str
                elif _OID_SYS_OBJECTID in oid_str:
                    values["sys_objectid"] = val_str

            sys_descr = values.get("sys_descr", "")
            sys_name = values.get("sys_name", ip)

            descr_lower = sys_descr.lower()
            if any(kw in descr_lower for kw in ("cisco", "juniper", "arista", "router", "switch", "firewall")):
                ci_type = "network_device"
            elif any(kw in descr_lower for kw in ("windows", "microsoft")):
                ci_type = "server"
            elif any(kw in descr_lower for kw in ("linux", "ubuntu", "centos", "debian", "rhel")):
                ci_type = "server"
            elif any(kw in descr_lower for kw in ("printer", "hp laserjet", "xerox")):
                ci_type = "printer"
            elif any(kw in descr_lower for kw in ("ups", "apc")):
                ci_type = "ups"
            else:
                ci_type = "network_device"

            discovered.append({
                "external_id": f"snmp:{ip}",
                "name": sys_name or ip,
                "ci_type": ci_type,
                "status": "active",
                "environment": "production",
                "ip_address": ip,
                "hostname": sys_name or ip,
                "version": "",
                "description": sys_descr[:500] if sys_descr else f"SNMP device at {ip}",
                "attributes": json.dumps({
                    "sys_location": values.get("sys_location", ""),
                    "sys_contact": values.get("sys_contact", ""),
                    "sys_objectid": values.get("sys_objectid", ""),
                    "snmp_version": version,
                    "community": community if version == "v2c" else "(SNMPv3)",
                }),
                "discovery_provider": PROVIDER_SNMP,
                "last_discovered_at": utcnow().isoformat(),
            })

        except Exception as exc:  # noqa: BLE001
            logger.debug("SNMP host %s error: %s", ip, exc)

    logger.info("SNMP discovery: %d activos encontrados de %d hosts sondeados", len(discovered), len(host_ips))
    return discovered


# ═══════════════════════════════════════════════════════════════════════════════
# SNMP NETWORK DISCOVERY (Enhanced with interface details)
# ═══════════════════════════════════════════════════════════════════════════════

def discover_snmp_network(provider_config: dict[str, Any]) -> list[dict[str, Any]]:
    """Enhanced SNMP discovery with interface-level data via ifTable walk."""
    try:
        from pysnmp.hlapi import (  # noqa: PLC0415
            CommunityData, ContextData, ObjectIdentity, ObjectType,
            SnmpEngine, UdpTransportTarget, getCmd,
        )
        from pysnmp.hlapi import UsmUserData, usmHMACSHAAuthProtocol, usmAesCfb128Protocol  # noqa: PLC0415
    except ImportError as exc:
        raise ImportError(
            "SNMP discovery requiere: pip install pysnmp"
        ) from exc

    import ipaddress  # noqa: PLC0415

    community = provider_config.get("community", "public")
    port = int(provider_config.get("port", 161))
    timeout = int(provider_config.get("timeout", 2))
    retries = int(provider_config.get("retries", 1))
    version = provider_config.get("version", "v2c")
    scan_interfaces = bool(provider_config.get("scan_interfaces", True))

    raw_hosts: list[str] = provider_config.get("hosts", [])

    host_ips: list[str] = []
    for h in raw_hosts:
        try:
            net = ipaddress.ip_network(h, strict=False)
            host_ips.extend(str(ip) for ip in list(net.hosts())[:1024])
        except ValueError:
            host_ips.append(h)

    discovered: list[dict] = []

    _OID_SYS_DESCR    = "1.3.6.1.2.1.1.1.0"
    _OID_SYS_NAME     = "1.3.6.1.2.1.1.5.0"
    _OID_SYS_LOCATION = "1.3.6.1.2.1.1.6.0"
    _OID_SYS_CONTACT  = "1.3.6.1.2.1.1.4.0"
    _OID_SYS_OBJECTID = "1.3.6.1.2.1.1.2.0"

    def _auth_data():
        if version == "v3":
            return UsmUserData(
                provider_config.get("v3_user", "admin"),
                authKey=provider_config.get("v3_auth_key", ""),
                privKey=provider_config.get("v3_priv_key", ""),
                authProtocol=usmHMACSHAAuthProtocol,
                privProtocol=usmAesCfb128Protocol,
            )
        return CommunityData(community, mpModel=1)  # noqa: S508

    engine = SnmpEngine()

    for ip in host_ips:
        try:
            transport = UdpTransportTarget((ip, port), timeout=timeout, retries=retries)
            oids = [
                ObjectType(ObjectIdentity(_OID_SYS_DESCR)),
                ObjectType(ObjectIdentity(_OID_SYS_NAME)),
                ObjectType(ObjectIdentity(_OID_SYS_LOCATION)),
                ObjectType(ObjectIdentity(_OID_SYS_CONTACT)),
                ObjectType(ObjectIdentity(_OID_SYS_OBJECTID)),
            ]
            error_indication, error_status, _, var_binds = next(
                getCmd(engine, _auth_data(), transport, ContextData(), *oids)
            )

            if error_indication or error_status:
                continue

            values: dict[str, str] = {}
            for var_bind in var_binds:
                oid_str = str(var_bind[0])
                val_str = str(var_bind[1])
                if _OID_SYS_DESCR in oid_str:
                    values["sys_descr"] = val_str
                elif _OID_SYS_NAME in oid_str:
                    values["sys_name"] = val_str
                elif _OID_SYS_LOCATION in oid_str:
                    values["sys_location"] = val_str
                elif _OID_SYS_CONTACT in oid_str:
                    values["sys_contact"] = val_str
                elif _OID_SYS_OBJECTID in oid_str:
                    values["sys_objectid"] = val_str

            sys_descr = values.get("sys_descr", "")
            sys_name  = values.get("sys_name", ip)

            descr_lower = sys_descr.lower()
            if any(kw in descr_lower for kw in ("cisco", "juniper", "arista", "router", "switch", "firewall")):
                ci_type = "network_device"
            elif any(kw in descr_lower for kw in ("windows", "microsoft")):
                ci_type = "server"
            elif any(kw in descr_lower for kw in ("linux", "ubuntu", "centos", "debian", "rhel")):
                ci_type = "server"
            elif any(kw in descr_lower for kw in ("printer", "hp laserjet", "xerox")):
                ci_type = "printer"
            elif any(kw in descr_lower for kw in ("ups", "apc")):
                ci_type = "ups"
            else:
                ci_type = "network_device"

            attributes: dict = {
                "sys_location": values.get("sys_location", ""),
                "sys_contact":  values.get("sys_contact", ""),
                "sys_objectid": values.get("sys_objectid", ""),
                "snmp_version": version,
                "community": community if version == "v2c" else "(SNMPv3)",
            }

            # Interface discovery via ifTable
            if scan_interfaces:
                ifaces = snmp_get_interfaces(ip, port, _auth_data(), engine)
                if ifaces:
                    attributes["interfaces"] = ifaces
                    attributes["interface_count"] = len(ifaces)
                    macs = [
                        iface.get("ifPhysAddress", "")
                        for iface in ifaces
                        if iface.get("ifPhysAddress") and iface.get("ifPhysAddress") != "0x"
                    ]
                    if macs:
                        attributes["mac_addresses"] = macs

            discovered.append({
                "external_id": f"snmp:{ip}",
                "name": sys_name or ip,
                "ci_type": ci_type,
                "status": "active",
                "environment": "production",
                "ip_address": ip,
                "hostname": sys_name or ip,
                "version": "",
                "description": sys_descr[:500] if sys_descr else f"SNMP device at {ip}",
                "attributes": json.dumps(attributes),
                "discovery_provider": PROVIDER_SNMP,
                "last_discovered_at": utcnow().isoformat(),
            })

        except Exception as exc:  # noqa: BLE001
            logger.debug("SNMP host %s error: %s", ip, exc)

    logger.info("SNMP network scan: %d activos encontrados de %d hosts sondeados", len(discovered), len(host_ips))
    return discovered


# ═══════════════════════════════════════════════════════════════════════════════
# ORCHESTRATION
# ═══════════════════════════════════════════════════════════════════════════════

def run_discovery_for_provider(db: Session, provider: CMDBDiscoveryProvider) -> CMDBDiscoveryJob:
    """Ejecuta discovery completo para un proveedor y registra el job."""
    job = CMDBDiscoveryJob(
        id=str(uuid4()),
        provider_id=provider.id,
        status="running",
        started_at=utcnow(),
        triggered_by="scheduler",
    )
    db.add(job)
    db.commit()

    try:
        config = load_config(provider)

        if provider.provider_type == PROVIDER_AWS:
            discovered = discover_aws(config)
        elif provider.provider_type == PROVIDER_K8S:
            discovered = discover_kubernetes(config)
        elif provider.provider_type == PROVIDER_VSPHERE:
            discovered = discover_vsphere(config)
        elif provider.provider_type == PROVIDER_AZURE:
            discovered = discover_azure(config)
        elif provider.provider_type == PROVIDER_GCP:
            discovered = discover_gcp(config)
        elif provider.provider_type == PROVIDER_SNMP:
            discovered = discover_snmp(config)
        else:
            raise ValueError(f"Proveedor no soportado: {provider.provider_type}")

        stats = reconcile_cis(db, discovered, provider.provider_type)

        job.status = "ok"
        job.cis_created = stats["created"]
        job.cis_updated = stats["updated"]
        job.cis_deactivated = stats["deactivated"]
        job.summary_json = json.dumps(stats)

    except Exception as exc:  # noqa: BLE001
        logger.error("Discovery error for provider %s: %s", provider.id, exc)
        job.status = "error"
        job.error_message = str(exc)[:2000]
    finally:
        job.finished_at = utcnow()
        provider.last_run_at = job.finished_at
        provider.last_run_status = job.status
        interval = max(1, getattr(provider, "scan_interval_minutes", 60) or 60)
        provider.next_run_at = job.finished_at + timedelta(minutes=interval)
        db.commit()

    return job


def run_all_active_discoveries(db: Session) -> list[dict]:
    """Ejecuta discovery para todos los proveedores activos."""
    providers = (
        db.query(CMDBDiscoveryProvider)
        .filter(CMDBDiscoveryProvider.is_active.is_(True))
        .all()
    )

    results = []
    for provider in providers:
        try:
            job = run_discovery_for_provider(db, provider)
            results.append({
                "provider_id": provider.id,
                "provider_name": provider.name,
                "provider_type": provider.provider_type,
                "job_id": job.id,
                "status": job.status,
                "created": job.cis_created,
                "updated": job.cis_updated,
                "deactivated": job.cis_deactivated,
                "error": job.error_message,
            })
        except Exception as exc:  # noqa: BLE001
            logger.error("Fatal error for provider %s: %s", provider.id, exc)
            results.append({
                "provider_id": provider.id,
                "provider_name": provider.name,
                "status": "error",
                "error": str(exc),
            })

    return results


def run_due_discoveries(db: Session) -> list[dict]:
    """Ejecuta discovery sólo para proveedores cuya ventana de ejecución ha vencido."""
    now = utcnow()
    providers = (
        db.query(CMDBDiscoveryProvider)
        .filter(
            CMDBDiscoveryProvider.is_active.is_(True),
            (CMDBDiscoveryProvider.next_run_at.is_(None))
            | (CMDBDiscoveryProvider.next_run_at <= now),
        )
        .all()
    )

    logger.info("run_due_discoveries: %d provider(s) due for scan", len(providers))
    results = []
    for provider in providers:
        try:
            job = run_discovery_for_provider(db, provider)
            results.append({
                "provider_id": provider.id,
                "provider_name": provider.name,
                "provider_type": provider.provider_type,
                "job_id": job.id,
                "status": job.status,
                "created": job.cis_created,
                "updated": job.cis_updated,
                "deactivated": job.cis_deactivated,
                "drift_detected": job.status == "ok",
                "error": job.error_message,
            })
        except Exception as exc:  # noqa: BLE001
            logger.error("Fatal error for provider %s: %s", provider.id, exc)
            results.append({
                "provider_id": provider.id,
                "provider_name": provider.name,
                "status": "error",
                "error": str(exc),
            })

    return results
