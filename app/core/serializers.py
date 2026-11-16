"""
ModelSerializer Base Class — Unify serialization patterns across services
==========================================================================
Proporciona una clase base reutilizable para serializar modelos SQLAlchemy
a diccionarios de respuesta JSON.

Ejemplo de uso:

    class VendorSerializer(ModelSerializer):
        fields = ['id', 'name', 'category', 'website', 'is_active']
        related_counts = {'contracts': 'contracts'}

        def get_extra_fields(self, obj):
            return {'status_label': obj.status.value if obj.status else None}

    # Uso
    vendor_dict = VendorSerializer(vendor).to_dict()
"""
from typing import Any, Dict, List, Optional
from app.core import timeutil


class ModelSerializer:
    """Base class para serializar modelos SQLAlchemy a diccionarios.

    Proporciona un patrón DRY para serialización consistente.
    Subclases deben definir:
        - fields: Lista de atributos simples a incluir
        - related_counts: Dict {relación: nombre_en_salida} para contar items
        - related_objects: Dict {relación: campo_id} para incluir relaciones

    Example:
        class UserSerializer(ModelSerializer):
            fields = ['id', 'name', 'email']
            related_counts = {'tasks': 'task_count'}
            related_objects = {'department': 'department_id'}
    """

    # Override these in subclasses
    fields: List[str] = []  # Campos simples a incluir
    related_counts: Dict[str, str] = {}  # {atributo: nombre_en_respuesta}
    related_objects: Dict[str, str] = {}  # {atributo: campo_id_a_incluir}

    def __init__(self, obj: Any):
        """Initialize serializer with a model instance."""
        self.obj = obj

    def to_dict(self) -> Dict[str, Any]:
        """Serializa el modelo a diccionario."""
        result = {}

        # 1. Campos simples
        for field in self.fields:
            if hasattr(self.obj, field):
                val = getattr(self.obj, field)
                result[field] = self._serialize_value(val)

        # 2. Conteos de relaciones
        for attr, name in self.related_counts.items():
            if hasattr(self.obj, attr):
                related = getattr(self.obj, attr)
                result[name] = len(related) if related else 0

        # 3. Objetos relacionados (id + nombre)
        for attr, id_field in self.related_objects.items():  # noqa: B007
            if hasattr(self.obj, attr):
                related = getattr(self.obj, attr)
                if related:
                    result[f"{attr}_id"] = getattr(related, 'id', None)
                    result[f"{attr}_name"] = self._get_name(related)
                else:
                    result[f"{attr}_id"] = None
                    result[f"{attr}_name"] = None

        # 4. Campos extra personalizados
        extra = self.get_extra_fields(self.obj)
        result.update(extra)

        return result

    def get_extra_fields(self, obj: Any) -> Dict[str, Any]:
        """Override en subclases para agregar campos personalizados."""
        return {}

    @staticmethod
    def _serialize_value(val: Any) -> Any:
        """Serializa un valor individual de forma inteligente.

        Maneja: datetime (ISO), Enum (value), dict/list (recursivo),
        y otros tipos (as-is). Preserva estructuras dict/list correctamente.
        """
        if val is None:
            return None
        if hasattr(val, 'isoformat'):  # datetime
            return val.isoformat()
        if isinstance(val, dict):  # preserve object shape for JSON fields
            return {k: ModelSerializer._serialize_value(v) for k, v in val.items()}
        if isinstance(val, (list, tuple, set)):  # list-like
            return [ModelSerializer._serialize_value(v) for v in val]
        if hasattr(val, 'value'):  # Enum
            return val.value
        return val

    @staticmethod
    def _get_name(obj: Any) -> Optional[str]:
        """Extrae el nombre de un objeto relacionado."""
        for attr in ('name', 'title', 'full_name', 'username', 'email'):
            if hasattr(obj, attr):
                return getattr(obj, attr)
        return None


# ═══════════════════════════════════════════════════════════════════════════════
# Ejemplo: Serializers para ALM Service
# ═══════════════════════════════════════════════════════════════════════════════

class VendorSerializer(ModelSerializer):
    """Serializer para Vendor."""
    fields = ['id', 'name', 'category', 'website', 'support_email', 'support_phone',
              'account_manager', 'account_number', 'country', 'tax_id', 'is_active', 'notes']
    related_counts = {'contracts': 'contracts_count'}


# Un contrato es de renovación urgente si renueva dentro de este número de días
# (hoy incluido). Lo usa el serializador y el filtro `renewal_urgent` del listado.
DIAS_RENOVACION_URGENTE = 60


class ContractSerializer(ModelSerializer):
    """Serializer para Contract."""
    fields = ['id', 'title', 'reference', 'type', 'status', 'vendor_id',
              'start_date', 'end_date', 'renewal_date', 'auto_renew', 'notice_days',
              'total_value', 'annual_value', 'billing_cycle', 'currency',
              'payment_method', 'po_number', 'cost_center_id', 'owner_id',
              'project_id', 'document_url', 'notes', 'tags', 'resolution_hours', 'response_hours']

    def get_extra_fields(self, obj):
        today = timeutil.today()
        days_to_renewal = None
        if obj.renewal_date:
            days_to_renewal = (obj.renewal_date - today).days
        return {
            'vendor_name': obj.vendor.name if obj.vendor else None,
            'owner_name': obj.owner.full_name if obj.owner else None,
            'days_to_renewal': days_to_renewal,
            'renewal_urgent': days_to_renewal is not None and 0 <= days_to_renewal <= DIAS_RENOVACION_URGENTE,
            'licenses_count': len(obj.licenses) if obj.licenses else 0,
        }


class LicenseSerializer(ModelSerializer):
    """Serializer para License."""
    fields = ['id', 'name', 'product_name', 'version', 'edition', 'type',
              'platform', 'status', 'vendor_id', 'contract_id', 'total_seats',
              'expiry_date', 'purchase_date', 'purchase_price', 'annual_cost',
              'cost_center_id', 'project_id', 'environment', 'is_compliance_req',
              'notes', 'metric', 'sku', 'tier', 'tier_rank', 'concurrent_peak', 'concurrent_peak_at',
              'amortization_months', 'rebillable', 'license_key_hint']

    def get_extra_fields(self, obj):
        # Fase 1 (16-11-2026): asientos = asignaciones de primer nivel activas o
        # pendientes, por su cantidad (las hijas de una bolsa consumen de ella).
        primeras = [a for a in (obj.assignments or []) if a.is_active and a.parent_id is None]
        used = sum(a.quantity or 0 for a in primeras)
        concurrente = obj.metric == "concurrent"
        sin_limite = obj.metric == "site"
        ocupados = (obj.concurrent_peak or 0) if concurrente else used
        avail = (obj.total_seats - ocupados) if obj.total_seats and not sin_limite else None
        status = obj.status
        if obj.expiry_date and obj.expiry_date < timeutil.today():
            status = "expired"
        elif obj.total_seats and not sin_limite and ocupados > obj.total_seats:
            status = "overallocated"
        elif used == 0 and obj.total_seats and obj.total_seats > 0:
            status = "unassigned"
        return {
            'vendor_name': obj.vendor.name if obj.vendor else None,
            'status': status,
            'used_seats': used,
            'available_seats': avail,
            'assignments_count': len(primeras),
            'pending_count': sum(1 for a in primeras if a.status == "pending"),
            'has_key': bool(obj._license_key),
            'days_to_expiry': (obj.expiry_date - timeutil.today()).days if obj.expiry_date else None,
        }


class AssetSerializer(ModelSerializer):
    """Serializer para Asset."""
    fields = ['id', 'name', 'type', 'brand', 'model', 'serial_number', 'asset_tag',
              'status', 'condition', 'assigned_to_id', 'location', 'department_id',
              'project_id', 'vendor_id', 'purchase_date', 'purchase_price', 'currency',
              'warranty_expiry', 'depreciation_years', 'ip_address', 'hostname', 'os',
              'cpu', 'ram_gb', 'storage_gb', 'notes', 'ci_id', 'eol_date', 'lease_expiry',
              'next_maintenance_date', 'maintenance_contract', 'refresh_ticket_id', 'cost_center_id',
              'residual_value', 'lease_monthly_cost', 'rebillable', 'disposal_date', 'disposal_reason',
              'disposal_method', 'disposal_value']

    def get_extra_fields(self, obj):
        age_years = None
        book_value = None
        if obj.purchase_date:
            age_years = (timeutil.today() - obj.purchase_date).days / 365
            if obj.purchase_price and obj.depreciation_years:
                depreciated = obj.purchase_price * (age_years / obj.depreciation_years)
                book_value = max(0, obj.purchase_price - depreciated)
        vigente = next((a for a in (obj.assignments or []) if a.status in ("active", "pending")), None)
        hoy = timeutil.today()
        if obj.purchase_date and obj.purchase_price and obj.depreciation_years and obj.residual_value:
            base = obj.purchase_price - obj.residual_value
            book_value = max(obj.residual_value, obj.purchase_price - base * (age_years / obj.depreciation_years))
        return {
            'current_assignment_id': vigente.id if vigente else None,
            'holder_type': vigente.holder_type if vigente else None,
            'holder_id': vigente.holder_id if vigente else None,
            'assignment_status': vigente.status if vigente else None,
            'assignment_mode': vigente.mode if vigente else None,
            'loan_due': vigente.valid_to.isoformat() if vigente and vigente.mode == "loan" and vigente.valid_to else None,
            'loan_overdue': bool(vigente and vigente.mode == "loan" and vigente.valid_to and vigente.valid_to < hoy
                                 and vigente.status == "active"),
            'assigned_to_name': obj.assigned_to.full_name if obj.assigned_to else None,
            'vendor_name': obj.vendor.name if obj.vendor else None,
            'warranty_expired': obj.warranty_expiry < timeutil.today() if obj.warranty_expiry else False,
            'age_years': round(age_years, 1) if age_years else None,
            'book_value': round(book_value, 2) if book_value is not None else None,
            'installed_licenses': len(obj.installs) if obj.installs else 0,
            'ci_name': obj.ci.name if obj.ci else None,
            'ci_code': obj.ci.code if obj.ci else None,
        }
