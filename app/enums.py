from enum import Enum


class TriggerMode(str, Enum):
    KM_ONLY = "km_only"
    DATE_ONLY = "date_only"
    KM_OR_DATE = "km_or_date"


class VehicleRole(str, Enum):
    OWNER = "owner"
    EDITOR = "editor"
    VIEWER = "viewer"


class WorkType(str, Enum):
    SERVICE = "service"
    REPAIR = "repair"
    UPGRADE = "upgrade"


class RenewalFrequency(str, Enum):
    MONTHLY = "monthly"
    ANNUAL = "annual"
    BIENNIAL = "biennial"
    ONE_TIME = "one_time"


class TaxInsuranceType(str, Enum):
    INSURANCE = "insurance"
    VIGNETTE = "vignette"
    CARBON_TAX = "carbon_tax"
    REGISTRATION = "registration"
    PARKING = "parking"
    TOLL_TAG = "toll_tag"
    OTHER = "other"
