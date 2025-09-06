from django.urls import path
from .views import upload_form_template, get_form_template

urlpatterns = [
    path('upload-form-template/', upload_form_template),
    path('get_form_template/', get_form_template),
]
