class ResourceNotFound(Exception):
    """Absent and foreign records intentionally share the same public response."""


class OrganizationConflict(Exception):
    """A safe conflict without database constraint or submitted-value details."""
