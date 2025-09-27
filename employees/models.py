from django.db import models
from django.conf import settings

class Employee(models.Model):
    USER_TYPE_CHOICES = [
        ("AREML", "AREML"),
        ("SWEAR", "SWEAR"),
        ("3rd Party", "3rd Party"),
        ("Customer", "Customer"),
    ]

    USER_ROLE_CHOICES = [
        ("DG SME", "DG SME"),
        ("AC SME", "AC SME"),
        ("Circle Head", "Circle Head"),   # 🔄 renamed from "state Head"
        ("IME Lead", "IME Lead"),
        ("Surveillance Lead", "Surveillance Lead"),
        ("Infra Lead", "Infra Lead"),
        ("Energy Lead", "Energy Lead"),
        ("HSSE Lead", "HSSE Lead"),
        ("Energy MIS", "Energy MIS"),
        ("Infra MIS", "Infra MIS"),
        ("Operational Lead", "Operational Lead"),
        ("Cluster Lead", "Cluster Lead"),
        ("Supervisor", "Supervisor"),
        ("Technician", "Technician"),
    ]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="employee_profile",
        null=True,
        blank=True,
    )

    company_name = models.CharField(max_length=255, default="Unknown Company")
    employee_id = models.CharField(max_length=50, unique=True, default="EMP-0000")
    passport_photo = models.ImageField(
        upload_to="employee/passports/", blank=True, null=True
    )
    signature_photo = models.ImageField(
        upload_to="employee/signatures/", blank=True, null=True
    )
    mobile_number = models.CharField(max_length=10, default="0000000000")

    user_type = models.CharField(
        max_length=50,
        choices=USER_TYPE_CHOICES,
        default="AREML",
    )

    user_role = models.CharField(
        max_length=100,
        choices=USER_ROLE_CHOICES,
        default="Technician",
    )

    manager = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="team_members",
        blank=True,
        null=True,
    )

    # 👇 This can stay if you want employee-level activation separate from user
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.user.first_name if self.user else 'Unknown'} ({self.employee_id})"
