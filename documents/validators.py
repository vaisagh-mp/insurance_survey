from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator

# Image extension validator
validate_image_extension = FileExtensionValidator(
    allowed_extensions=['jpg', 'jpeg', 'png'],
    message="Only JPG, JPEG, and PNG image files are allowed."
)

# Document extension validator (PDF and standard image formats)
validate_document_extension = FileExtensionValidator(
    allowed_extensions=['pdf', 'jpg', 'jpeg', 'png'],
    message="Only PDF, JPG, JPEG, and PNG files are allowed."
)

# Shared file size validator (max 10MB)
def validate_file_size(value):
    """Ensure uploaded file does not exceed 10 megabytes."""
    max_size_mb = 10
    max_size_bytes = max_size_mb * 1024 * 1024
    if value.size > max_size_bytes:
        raise ValidationError(
            f"File size cannot exceed {max_size_mb}MB. "
            f"Current file size: {value.size / (1024 * 1024):.2f}MB."
        )

# Centralized composite validators (Type + Size)
def validate_image_file(value):
    """Centralized validator for image files: jpg, jpeg, png up to 10MB."""
    validate_image_extension(value)
    validate_file_size(value)


def validate_document_file(value):
    """Centralized validator for document files: pdf, jpg, jpeg, png up to 10MB."""
    validate_document_extension(value)
    validate_file_size(value)


# Backward-compatible aliases
validate_image_size = validate_file_size
validate_file_extension = validate_document_extension
