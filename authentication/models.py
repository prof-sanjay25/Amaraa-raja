from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from datetime import timedelta

import re

class User(AbstractUser):
    STATE_CHOICES = [
        ('Andhra Pradesh', 'Andhra Pradesh'),
        ('Telangana', 'Telangana'),
        ('Hyderabad', 'Hyderabad'),
        ('Odisha', 'Odisha'),
    ]

    role = models.CharField(max_length=20, choices=[
        ('superadmin', 'SuperAdmin'),
        ('admin', 'Admin'),
        ('employee', 'Employee'),
    ])
    state = models.CharField(max_length=100, choices=STATE_CHOICES)
    global_id = models.CharField(max_length=20, unique=True, blank=True, null=True)
    state_user_id = models.CharField(max_length=20, unique=True, blank=True, null=True)

    passport_photo = models.ImageField(upload_to='passport_photos/', blank=True, null=True)
    signature_photo = models.ImageField(upload_to='signature_photos/', blank=True, null=True)

    def save(self, *args, **kwargs):
        is_new = self._state.adding

        if is_new or (not self.state_user_id and self.role and self.state):
            if not self.global_id:
                last_user = User.objects.order_by('-id').first()
                next_id = (last_user.id if last_user else 0) + 1
                self.global_id = f"USR-{next_id:04d}"

            if not self.state_user_id:
                prefix = self.state[:2].upper()
                role_code = 'ADM' if self.role == 'admin' else 'EMP' if self.role == 'employee' else 'SUP'
                count = 1
                while True:
                    potential_id = f"{prefix}-{role_code}-{count:03d}"
                    if not User.objects.filter(state_user_id=potential_id).exists():
                        self.state_user_id = potential_id
                        break
                    count += 1

        super().save(*args, **kwargs)

    @staticmethod
    def validate_password_strength(password):
        """
        Custom password validation:
        - At least 8 characters
        - At least 1 uppercase letter
        - At least 1 number
        - At least 1 special character
        """
        if len(password) < 8:
            raise ValidationError("Password must be at least 8 characters long.")
        if not re.search(r"[A-Z]", password):
            raise ValidationError("Password must contain at least one uppercase letter.")
        if not re.search(r"\d", password):
            raise ValidationError("Password must contain at least one number.")
        if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", password):
            raise ValidationError("Password must contain at least one special character.")


    reset_otp = models.CharField(max_length=6, blank=True, null=True)
    reset_otp_created_at = models.DateTimeField(blank=True, null=True)

    def is_reset_otp_valid(self, otp):
        """Check OTP correctness and 10 min expiry."""
        if not self.reset_otp or not self.reset_otp_created_at:
            return False
        if str(self.reset_otp) != str(otp):
            return False
        expiry_time = self.reset_otp_created_at + timedelta(minutes=10)
        return timezone.now() <= expiry_time