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
              'account_manager', 'account_number', 'country', 'is_active', 'notes']
    related_counts = {'contracts': 'contracts_count'}


class ContractSerializer(ModelSerializer):
    """Serializer para Contract."""
    fields = ['id', 'title', 'reference', 'type', 'status', 'vendor_id',
              'start_date', 'end_date', 'renewal_date', 'auto_renew', 'notice_days',
              'total_value', 'annual_value', 'billing_cycle', 'currency',
              'payment_method', 'po_number', 'cost_center_id', 'owner_id',
              'project_id', 'document_url', 'notes', 'tags']

    def get_extra_fields(self, obj):
        from datetime import date
        today = date.today()
        days_to_renewal = None
        if obj.renewal_date:
            days_to_renewal = (obj.renewal_date - today).days
        return {
            'vendor_name': obj.vendor.name if obj.vendor else None,
            'owner_name': obj.owner.full_name if obj.owner else None,
            'days_to_renewal': days_to_renewal,
            'renewal_urgent': days_to_renewal is not None and 0 <= days_to_renewal <= 60,
            'licenses_count': len(obj.licenses) if obj.licenses else 0,
        }


class LicenseSerializer(ModelSerializer):
    """Serializer para License."""
    fields = ['id', 'name', 'product_name', 'version', 'edition', 'type',
              'platform', 'status', 'vendor_id', 'contract_id', 'total_seats',
              'expiry_date', 'purchase_date', 'purchase_price', 'annual_cost',
              'cost_center_id', 'project_id', 'environment', 'is_compliance_req',
              'notes']

    def get_extra_fields(self, obj):
        from datetime import date
        used = sum(1 for a in obj.assignments if a.is_active) if obj.assignments else 0
        avail = (obj.total_seats - used) if obj.total_seats else None
        status = obj.status
        if obj.expiry_date and obj.expiry_date < date.today():
            status = "expired"
        elif obj.total_seats and used > obj.total_seats:
            status = "overallocated"
        elif used == 0 and obj.total_seats and obj.total_seats > 0:
            status = "unassigned"
        return {
            'vendor_name': obj.vendor.name if obj.vendor else None,
            'status': status,
            'used_seats': used,
            'available_seats': avail,
            'assignments_count': used,
            'days_to_expiry': (obj.expiry_date - date.today()).days if obj.expiry_date else None,
        }


class AssetSerializer(ModelSerializer):
    """Serializer para Asset."""
    fields = ['id', 'name', 'type', 'brand', 'model', 'serial_number', 'asset_tag',
              'status', 'condition', 'assigned_to_id', 'location', 'department_id',
              'project_id', 'vendor_id', 'purchase_date', 'purchase_price', 'currency',
              'warranty_expiry', 'depreciation_years', 'ip_address', 'hostname', 'os',
              'cpu', 'ram_gb', 'storage_gb', 'notes']

    def get_extra_fields(self, obj):
        from datetime import date
        age_years = None
        book_value = None
        if obj.purchase_date:
            age_years = (date.today() - obj.purchase_date).days / 365
            if obj.purchase_price and obj.depreciation_years:
                depreciated = obj.purchase_price * (age_years / obj.depreciation_years)
                book_value = max(0, obj.purchase_price - depreciated)
        return {
            'assigned_to_name': obj.assigned_to.full_name if obj.assigned_to else None,
            'vendor_name': obj.vendor.name if obj.vendor else None,
            'warranty_expired': obj.warranty_expiry < date.today() if obj.warranty_expiry else False,
            'age_years': round(age_years, 1) if age_years else None,
            'book_value': round(book_value, 2) if book_value is not None else None,
            'installed_licenses': len(obj.installs) if obj.installs else 0,
        }
