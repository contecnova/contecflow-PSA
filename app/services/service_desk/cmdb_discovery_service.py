"""
CMDB Auto-Discovery Service — Fase 1 ITSM Enhancement
======================================================
Descubre activos IT de AWS, Azure, GCP, Kubernetes y vSphere y los reconcilia
con el inventario CMDB.

Dependencias opcionales:
  - boto3       (pip install boto3)     → AWS discovery
    - google-cloud-compute (pip install google-cloud-compute) → GCP discovery
  - kubernetes  (pip install kubernetes) → K8s discovery

Si alguna librería no está instalada, ese proveedor lanza ImportError con mensaje claro.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models.cmdb import CMDBDiscoveryJob, CMDBDiscoveryProvider, CMDBItem

logger = logging.getLogger(__name__)

# ── Constantes ────────────────────────────────────────────────────────────────

_PROVIDER_AWS = "aws"
_PROVIDER_K8S = "kubernetes"
_PROVIDER_VSPHERE = "vsphere"
_PROVIDER_AZURE = "azure"
_PROVIDER_GCP = "gcp"
_PROVIDER_SNMP = "snmp"
_SUPPORTED_PROVIDERS = {
    _PROVIDER_AWS,
    _PROVIDER_K8S,
    _PROVIDER_VSPHERE,
    _PROVIDER_AZURE,
    _PROVIDER_GCP,
    _PROVIDER_SNMP,
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


def _load_config(provider: CMDBDiscoveryProvider) -> dict:
    """Devuelve config_json parseado como dict. Devuelve {} si vacío."""
    raw = provider.config_json or "{}"
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}


# ── AWS Discovery ─────────────────────────────────────────────────────────────

def discover_aws(provider_config: dict) -> list[dict]:
    """Descubre activos EC2 + RDS en AWS.

    Args:
        provider_config: dict con claves opcionales:
            - aws_access_key_id / aws_secret_access_key / region_name
            - Si vacío, usa credenciales del entorno (IAM role / ~/.aws).

    Returns:
        list[dict] con campos normalizados (external_id, name, ci_type, ip_address, …).
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
        session_kwargs["aws_secret_access_key"] = provider_config.get(
            "aws_secret_access_key", ""
        )

    boto_session = boto3.Session(**session_kwargs)
    discovered: list[dict] = []

    # ── EC2 instances ──────────────────────────────────────────────────────────
    try:
        ec2 = boto_session.resource("ec2")
        for instance in ec2.instances.all():
            name_tag = next(
                (t["Value"] for t in (instance.tags or []) if t["Key"] == "Name"),
                instance.id,
            )
            discovered.append(
                {
                    "external_id": instance.id,
                    "name": name_tag,
                    "ci_type": "server",
                    "status": "active" if instance.state["Name"] == "running" else "maintenance",
                    "environment": next(
                        (
                            t["Value"]
                            for t in (instance.tags or [])
                            if t["Key"].lower() in ("env", "environment")
                        ),
                        "production",
                    ),
                    "ip_address": instance.private_ip_address or "",
                    "hostname": instance.public_dns_name or instance.id,
                    "version": instance.instance_type,
                    "description": f"AWS EC2 {instance.instance_type} — {instance.state['Name']}",
                    "attributes": json.dumps(
                        {
                            "instance_type": instance.instance_type,
                            "ami": instance.image_id,
                            "az": instance.placement.get("AvailabilityZone", ""),
                            "vpc_id": instance.vpc_id or "",
                        }
                    ),
                    "discovery_provider": _PROVIDER_AWS,
                    "last_discovered_at": _utcnow().isoformat(),
                }
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("AWS EC2 discovery error: %s", exc)

    # ── RDS instances ──────────────────────────────────────────────────────────
    try:
        rds_client = boto_session.client("rds")
        paginator = rds_client.get_paginator("describe_db_instances")
        for page in paginator.paginate():
            for db in page.get("DBInstances", []):
                discovered.append(
                    {
                        "external_id": db["DBInstanceIdentifier"],
                        "name": db["DBInstanceIdentifier"],
                        "ci_type": "database",
                        "status": "active" if db["DBInstanceStatus"] == "available" else "maintenance",
                        "environment": "production",
                        "ip_address": db.get("Endpoint", {}).get("Address", ""),
                        "hostname": db.get("Endpoint", {}).get("Address", ""),
                        "version": f"{db.get('Engine', '')} {db.get('EngineVersion', '')}",
                        "description": f"AWS RDS {db.get('Engine', '')} — {db['DBInstanceStatus']}",
                        "attributes": json.dumps(
                            {
                                "engine": db.get("Engine", ""),
                                "engine_version": db.get("EngineVersion", ""),
                                "instance_class": db.get("DBInstanceClass", ""),
                                "multi_az": db.get("MultiAZ", False),
                            }
                        ),
                        "discovery_provider": _PROVIDER_AWS,
                        "last_discovered_at": _utcnow().isoformat(),
                    }
                )
    except Exception as exc:  # noqa: BLE001
        logger.warning("AWS RDS discovery error: %s", exc)

    logger.info("AWS discovery: %d activos encontrados", len(discovered))
    return discovered


# ── Kubernetes Discovery ──────────────────────────────────────────────────────

def discover_kubernetes(provider_config: dict) -> list[dict]:
    """Descubre nodos y namespaces de un cluster Kubernetes.

    Args:
        provider_config: dict con claves opcionales:
            - kubeconfig_path: ruta al fichero kubeconfig.
            - in_cluster: True para usar service account del pod.
            - Si vacío, usa ~/.kube/config.

    Returns:
        list[dict] con campos normalizados.
    """
    try:
        from kubernetes import client as k8s_client  # noqa: PLC0415
        from kubernetes import config as k8s_config  # noqa: PLC0415
    except ImportError as exc:
        raise ImportError(
            "El proveedor Kubernetes requiere el cliente oficial. "
            "Instálalo con: pip install kubernetes"
        ) from exc

    # Cargar config
    try:
        if provider_config.get("in_cluster"):
            k8s_config.load_incluster_config()
        elif provider_config.get("kubeconfig_path"):
            k8s_config.load_kube_config(config_file=provider_config["kubeconfig_path"])
        else:
            k8s_config.load_kube_config()
    except Exception as exc:
        raise RuntimeError(f"No se pudo cargar kubeconfig: {exc}") from exc

    v1 = k8s_client.CoreV1Api()
    discovered: list[dict] = []

    # ── Nodes ──────────────────────────────────────────────────────────────────
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
            discovered.append(
                {
                    "external_id": meta.uid,
                    "name": meta.name,
                    "ci_type": "server",
                    "status": "active" if is_ready else "maintenance",
                    "environment": meta.labels.get("environment", "production")
                    if meta.labels
                    else "production",
                    "ip_address": internal_ip,
                    "hostname": meta.name,
                    "version": node_info.kubelet_version if node_info else "",
                    "description": f"K8s Node — kubelet {getattr(node_info, 'kubelet_version', '')}",
                    "attributes": json.dumps(
                        {
                            "os": getattr(node_info, "os_image", ""),
                            "arch": getattr(node_info, "architecture", ""),
                            "container_runtime": getattr(node_info, "container_runtime_version", ""),
                            "labels": meta.labels or {},
                        }
                    ),
                    "discovery_provider": _PROVIDER_K8S,
                    "last_discovered_at": _utcnow().isoformat(),
                }
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("K8s nodes discovery error: %s", exc)

    # ── Namespaces (mapped as service CIs) ────────────────────────────────────
    try:
        for ns in v1.list_namespace().items:
            meta = ns.metadata
            phase = ns.status.phase if ns.status else "Active"
            discovered.append(
                {
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
                    "discovery_provider": _PROVIDER_K8S,
                    "last_discovered_at": _utcnow().isoformat(),
                }
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("K8s namespaces discovery error: %s", exc)

    logger.info("K8s discovery: %d activos encontrados", len(discovered))
    return discovered


# ── vSphere Discovery (Sprint 17-18) ─────────────────────────────────────────

def discover_vsphere(provider_config: dict) -> list[dict]:
    """Descubre VMs y hosts ESXi de una infraestructura VMware vSphere/vCenter.

    Dependencia opcional: ``pyVmomi``  (pip install pyVmomi).
    Si no está disponible, hace un discovery simulado con datos de muestra
    (útil para entornos de desarrollo / demo).

    Args:
        provider_config: dict con claves:
            - host (str): FQDN o IP del vCenter / ESXi
            - user (str): usuario de vCenter
            - password (str): contraseña
            - port (int, opcional): defecto 443
            - disable_ssl_verification (bool, opcional): defecto False

    Returns:
        list[dict] de CIs normalizados.
    """
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
                    "discovery_provider": _PROVIDER_VSPHERE,
                    "last_discovered_at": _utcnow().isoformat(),
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
                    "discovery_provider": _PROVIDER_VSPHERE,
                    "last_discovered_at": _utcnow().isoformat(),
                })

        container.Destroy()
        Disconnect(si)

    except ImportError:
        logger.warning(
            "pyVmomi no instalado — vSphere discovery no disponible. "
            "Instálalo con: pip install pyVmomi"
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("vSphere discovery error: %s", exc)

    logger.info("vSphere discovery: %d activos encontrados", len(discovered))
    return discovered


# ── Azure Discovery (Sprint 17-18) ───────────────────────────────────────────

def discover_azure(provider_config: dict) -> list[dict]:
    """Descubre VMs, bases de datos y recursos de red de Azure Resource Manager.

    Dependencia opcional: ``azure-mgmt-compute``, ``azure-mgmt-network``,
    ``azure-identity`` (pip install azure-mgmt-compute azure-mgmt-network azure-identity).

    Args:
        provider_config: dict con claves:
            - subscription_id (str): ID de suscripción Azure
            - tenant_id / client_id / client_secret (str): credenciales Service Principal
              (si vacíos, usa DefaultAzureCredential — env vars, managed identity, etc.)
            - resource_group (str, opcional): filtrar por resource group

    Returns:
        list[dict] de CIs normalizados.
    """
    subscription_id = provider_config.get("subscription_id", "")
    resource_group = provider_config.get("resource_group")  # optional filter
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

        # ── Azure VMs ──────────────────────────────────────────────────────────
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
                    vm.id.split("/")[4],  # resource group from resource ID
                    vm.name,
                )
                for status in (instance_view.statuses or []):
                    if status.code and status.code.startswith("PowerState/"):
                        power_state = status.code.replace("PowerState/", "")
                        break
            except Exception:  # noqa: BLE001
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
                "discovery_provider": _PROVIDER_AZURE,
                "last_discovered_at": _utcnow().isoformat(),
            })

    except Exception as exc:  # noqa: BLE001
        logger.error("Azure discovery error: %s", exc)

    logger.info("Azure discovery: %d activos encontrados", len(discovered))
    return discovered


# ── GCP Discovery ────────────────────────────────────────────────────────────

def discover_gcp(provider_config: dict) -> list[dict]:
    """Descubre activos de Google Cloud (Compute Engine VMs).

    Dependencia opcional: ``google-cloud-compute``
    (pip install google-cloud-compute).

    Args:
        provider_config: dict con claves:
            - project_id (str, requerido)
            - service_account_file (str, opcional): ruta JSON credenciales

    Returns:
        list[dict] de CIs normalizados.
    """
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
                    "discovery_provider": _PROVIDER_GCP,
                    "last_discovered_at": _utcnow().isoformat(),
                })
    except Exception as exc:  # noqa: BLE001
        logger.error("GCP discovery error: %s", exc)

    logger.info("GCP discovery: %d activos encontrados", len(discovered))
    return discovered


# ── SNMP Discovery ────────────────────────────────────────────────────────────

def discover_snmp(provider_config: dict) -> list[dict]:
    """Descubre activos de red mediante SNMP v2c/v3.

    Realiza SNMP walk sobre las OIDs estándar de sistema (sysDescr, sysName,
    sysLocation, sysContact, ifTable) para cada host del rango indicado.

    Dependencia opcional: ``pysnmp`` (pip install pysnmp).

    Args:
        provider_config: dict con claves:
            - hosts (list[str]): lista de IPs o rangos CIDR (e.g. ["192.168.1.0/24"])
            - community (str): community string SNMP v2c (default "public")
            - port (int): puerto UDP (default 161)
            - timeout (int): segundos por host (default 2)
            - retries (int): reintentos por host (default 1)
            - version (str): "v2c" | "v3" (default "v2c")
            - v3_user / v3_auth_key / v3_priv_key: credenciales SNMPv3

    Returns:
        list[dict] de CIs normalizados.
    """
    try:
        from pysnmp.hlapi import (  # noqa: PLC0415
            CommunityData, ContextData, ObjectIdentity, ObjectType,
            SnmpEngine, UdpTransportTarget, bulkCmd, getCmd,
        )
        from pysnmp.hlapi import UsmUserData, usmHMACSHAAuthProtocol, usmAesCfb128Protocol  # noqa: PLC0415
    except ImportError as exc:
        raise ImportError(
            "SNMP discovery requiere pysnmp. Instálalo con: pip install pysnmp"
        ) from exc

    import ipaddress  # noqa: PLC0415

    community = provider_config.get("community", "public")
    port = int(provider_config.get("port", 161))
    timeout = int(provider_config.get("timeout", 2))
    retries = int(provider_config.get("retries", 1))
    version = provider_config.get("version", "v2c")

    raw_hosts: list[str] = provider_config.get("hosts", [])

    # Expand CIDR ranges into individual IPs (cap at 1024 to avoid huge sweeps)
    host_ips: list[str] = []
    for h in raw_hosts:
        try:
            net = ipaddress.ip_network(h, strict=False)
            host_ips.extend(str(ip) for ip in list(net.hosts())[:1024])
        except ValueError:
            host_ips.append(h)

    discovered: list[dict] = []

    # OIDs we query per host
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
        return CommunityData(community, mpModel=1)  # mpModel=1 → SNMPv2c

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
                continue  # host unreachable or SNMP error — skip silently

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

            # Infer CI type from sysDescr
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
                "discovery_provider": _PROVIDER_SNMP,
                "last_discovered_at": _utcnow().isoformat(),
            })

        except Exception as exc:  # noqa: BLE001
            logger.debug("SNMP host %s error: %s", ip, exc)

    logger.info("SNMP discovery: %d activos encontrados de %d hosts sondeados", len(discovered), len(host_ips))
    return discovered


# ── Reconciliation ────────────────────────────────────────────────────────────

def reconcile_cis(
    db: Session,
    discovered_cis: list[dict],
    provider_type: str,
) -> dict[str, int]:
    """Compara CIs descubiertos con los existentes en la BD y aplica cambios.

    Estrategia de matching: external_id + discovery_provider (únicos juntos).
    - Si no existe → CREATE.
    - Si existe y hay cambios → UPDATE (name, status, ip, hostname, version, attributes).
    - CIs que pertenecen al proveedor pero no aparecen en el scan → deactivate (status="decommissioned").

    Returns:
        dict con contadores: {"created": N, "updated": N, "deactivated": N}
    """
    created = updated = deactivated = 0
    now = _utcnow()

    discovered_ext_ids = {ci["external_id"] for ci in discovered_cis}

    for ci_data in discovered_cis:
        ext_id = ci_data["external_id"]
        existing: CMDBItem | None = (
            db.query(CMDBItem)
            .filter(
                CMDBItem.external_id == ext_id,
                CMDBItem.discovery_provider == provider_type,
            )
            .first()
        )

        if existing is None:
            # CREATE
            new_ci = CMDBItem(
                id=str(uuid4()),
                name=ci_data.get("name", ext_id),
                ci_type=ci_data.get("ci_type", "server"),
                status=ci_data.get("status", "active"),
                environment=ci_data.get("environment", "production"),
                ip_address=ci_data.get("ip_address"),
                hostname=ci_data.get("hostname"),
                version=ci_data.get("version"),
                description=ci_data.get("description"),
                attributes=ci_data.get("attributes"),
                external_id=ext_id,
                discovery_provider=provider_type,
                is_discovered=True,
                last_discovered_at=now,
            )
            db.add(new_ci)
            created += 1
        else:
            # UPDATE if any field changed
            changed = False
            for field in ("name", "status", "ip_address", "hostname", "version",
                          "description", "attributes", "environment"):
                new_val = ci_data.get(field)
                if new_val is not None and getattr(existing, field) != new_val:
                    setattr(existing, field, new_val)
                    changed = True
            existing.last_discovered_at = now
            existing.is_discovered = True
            if changed:
                updated += 1

    # Deactivate stale CIs (visible to this provider but not seen in current scan)
    stale = (
        db.query(CMDBItem)
        .filter(
            CMDBItem.discovery_provider == provider_type,
            CMDBItem.is_discovered.is_(True),
            CMDBItem.status != "decommissioned",
        )
        .all()
    )
    for ci in stale:
        if ci.external_id not in discovered_ext_ids:
            ci.status = "decommissioned"
            deactivated += 1

    db.flush()
    logger.info(
        "Reconcile [%s]: created=%d, updated=%d, deactivated=%d",
        provider_type,
        created,
        updated,
        deactivated,
    )
    return {"created": created, "updated": updated, "deactivated": deactivated}


# ── Orchestration ─────────────────────────────────────────────────────────────

def run_discovery_for_provider(db: Session, provider: CMDBDiscoveryProvider) -> CMDBDiscoveryJob:
    """Ejecuta discovery completo para un proveedor y registra el job.

    Commits the job record. Caller must NOT commit before calling this function.
    After this call, the session is in a clean state (committed).

    Returns:
        CMDBDiscoveryJob con el resultado del run.
    """
    job = CMDBDiscoveryJob(
        id=str(uuid4()),
        provider_id=provider.id,
        status="running",
        started_at=_utcnow(),
        triggered_by="scheduler",
    )
    db.add(job)
    db.commit()

    try:
        config = _load_config(provider)

        if provider.provider_type == _PROVIDER_AWS:
            discovered = discover_aws(config)
        elif provider.provider_type == _PROVIDER_K8S:
            discovered = discover_kubernetes(config)
        elif provider.provider_type == _PROVIDER_VSPHERE:
            discovered = discover_vsphere(config)
        elif provider.provider_type == _PROVIDER_AZURE:
            discovered = discover_azure(config)
        elif provider.provider_type == _PROVIDER_GCP:
            discovered = discover_gcp(config)
        elif provider.provider_type == _PROVIDER_SNMP:
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
        job.finished_at = _utcnow()
        provider.last_run_at = job.finished_at
        provider.last_run_status = job.status
        db.commit()

    return job


def run_all_active_discoveries(db: Session) -> list[dict]:
    """Ejecuta discovery para todos los proveedores activos.

    Llamado desde el Celery beat task `cmdb_discovery_run`.

    Returns:
        Lista de resúmenes por proveedor.
    """
    providers = (
        db.query(CMDBDiscoveryProvider)
        .filter(CMDBDiscoveryProvider.is_active.is_(True))
        .all()
    )

    results = []
    for provider in providers:
        try:
            job = run_discovery_for_provider(db, provider)
            results.append(
                {
                    "provider_id": provider.id,
                    "provider_name": provider.name,
                    "provider_type": provider.provider_type,
                    "job_id": job.id,
                    "status": job.status,
                    "created": job.cis_created,
                    "updated": job.cis_updated,
                    "deactivated": job.cis_deactivated,
                    "error": job.error_message,
                }
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("Fatal error for provider %s: %s", provider.id, exc)
            results.append(
                {
                    "provider_id": provider.id,
                    "provider_name": provider.name,
                    "status": "error",
                    "error": str(exc),
                }
            )

    return results


def get_reconciliation_health(db: Session, provider_type: str | None = None) -> dict:
    """Build reconciliation health metrics for discovered CIs.

    Metrics:
      - total_discovered: discovered CIs in CMDB
      - active_discovered: discovered CIs currently active/maintenance
      - stale_discovered: discovered CIs decommissioned by reconciliation
      - duplicate_external_ids: repeated (provider, external_id) pairs
      - by_provider: per-provider counts
    """
    q = db.query(CMDBItem).filter(CMDBItem.is_discovered.is_(True))
    if provider_type:
        q = q.filter(CMDBItem.discovery_provider == provider_type)

    rows = q.all()
    total_discovered = len(rows)
    stale_discovered = sum(1 for r in rows if r.status == "decommissioned")
    active_discovered = total_discovered - stale_discovered

    dup_q = (
        db.query(
            CMDBItem.discovery_provider,
            CMDBItem.external_id,
            func.count(CMDBItem.id).label("n"),
        )
        .filter(CMDBItem.is_discovered.is_(True), CMDBItem.external_id.isnot(None))
        .group_by(CMDBItem.discovery_provider, CMDBItem.external_id)
        .having(func.count(CMDBItem.id) > 1)
    )
    if provider_type:
        dup_q = dup_q.filter(CMDBItem.discovery_provider == provider_type)

    duplicate_external_ids = dup_q.count()

    provider_counts = {}
    for r in rows:
        key = r.discovery_provider or "unknown"
        if key not in provider_counts:
            provider_counts[key] = {
                "total": 0,
                "active": 0,
                "decommissioned": 0,
            }
        provider_counts[key]["total"] += 1
        if r.status == "decommissioned":
            provider_counts[key]["decommissioned"] += 1
        else:
            provider_counts[key]["active"] += 1

    score = 100
    if total_discovered > 0:
        stale_ratio = stale_discovered / total_discovered
        score -= int(stale_ratio * 35)
    score -= min(duplicate_external_ids * 10, 35)
    score = max(score, 0)

    return {
        "provider_filter": provider_type,
        "total_discovered": total_discovered,
        "active_discovered": active_discovered,
        "stale_discovered": stale_discovered,
        "duplicate_external_ids": duplicate_external_ids,
        "reconciliation_score": score,
        "by_provider": provider_counts,
    }


def _string_similarity(a: str | None, b: str | None) -> float:
    aa = (a or "").strip().lower()
    bb = (b or "").strip().lower()
    if not aa or not bb:
        return 0.0
    return SequenceMatcher(None, aa, bb).ratio()


def ci_similarity_score(ci_a: CMDBItem, ci_b: CMDBItem) -> float:
    """Similarity score in [0,1] for duplicate candidate detection."""
    name_score = _string_similarity(ci_a.name, ci_b.name)
    host_score = _string_similarity(ci_a.hostname, ci_b.hostname)
    ip_score = 1.0 if ci_a.ip_address and ci_a.ip_address == ci_b.ip_address else 0.0
    type_score = 1.0 if ci_a.ci_type == ci_b.ci_type else 0.0
    env_score = 1.0 if ci_a.environment == ci_b.environment else 0.0
    return round(name_score * 0.45 + host_score * 0.25 + ip_score * 0.2 + type_score * 0.07 + env_score * 0.03, 4)


def deduplicate_candidates(
    db: Session,
    *,
    provider_type: str | None = None,
    min_confidence: float = 0.85,
) -> list[dict]:
    """Find possible duplicates and return merge candidates with confidence score."""
    q = db.query(CMDBItem).filter(CMDBItem.is_discovered.is_(True), CMDBItem.status != "decommissioned")
    if provider_type:
        q = q.filter(CMDBItem.discovery_provider == provider_type)
    rows = q.order_by(CMDBItem.discovery_provider.asc(), CMDBItem.name.asc()).all()

    candidates: list[dict] = []
    for i in range(len(rows)):
        a = rows[i]
        for j in range(i + 1, len(rows)):
            b = rows[j]
            if provider_type and (a.discovery_provider != b.discovery_provider):
                continue
            score = ci_similarity_score(a, b)
            if score < min_confidence:
                continue
            keeper, duplicate = (a, b)
            if (b.last_discovered_at or datetime.min) > (a.last_discovered_at or datetime.min):
                keeper, duplicate = (b, a)

            candidates.append(
                {
                    "provider": a.discovery_provider or b.discovery_provider,
                    "confidence": score,
                    "keeper": {
                        "id": keeper.id,
                        "name": keeper.name,
                        "hostname": keeper.hostname,
                        "ip_address": keeper.ip_address,
                    },
                    "duplicate": {
                        "id": duplicate.id,
                        "name": duplicate.name,
                        "hostname": duplicate.hostname,
                        "ip_address": duplicate.ip_address,
                    },
                }
            )
    candidates.sort(key=lambda x: x["confidence"], reverse=True)
    return candidates


def auto_merge_duplicates(
    db: Session,
    *,
    provider_type: str | None = None,
    min_confidence: float = 0.85,
    limit: int = 100,
) -> dict:
    """Apply automatic deduplication by decommissioning likely duplicate CIs."""
    candidates = deduplicate_candidates(
        db,
        provider_type=provider_type,
        min_confidence=min_confidence,
    )[: max(1, limit)]

    merged = 0
    applied: list[dict] = []
    for c in candidates:
        dup = db.query(CMDBItem).filter(CMDBItem.id == c["duplicate"]["id"]).first()
        keep = db.query(CMDBItem).filter(CMDBItem.id == c["keeper"]["id"]).first()
        if not dup or not keep or dup.status == "decommissioned":
            continue

        dup.status = "decommissioned"
        note = f"[auto-merge] merged_into={keep.id} confidence={c['confidence']}"
        dup.description = f"{dup.description or ''}\n{note}".strip()
        merged += 1
        applied.append(c)

    db.flush()
    return {
        "provider_filter": provider_type,
        "min_confidence": min_confidence,
        "candidates": len(candidates),
        "merged": merged,
        "applied": applied,
    }
