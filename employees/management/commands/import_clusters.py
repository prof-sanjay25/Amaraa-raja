import csv
from django.core.management.base import BaseCommand
from employees.models import SiteData

class Command(BaseCommand):
    help = 'Import site data from Global ID.csv'

    def handle(self, *args, **kwargs):
        file_path = 'Global ID.csv'  # Adjust path if in subfolder

        with open(file_path, newline='', encoding='latin1') as csvfile:

            reader = csv.DictReader(csvfile)
            count = 0
            for row in reader:
                global_id = row['Global ID'].strip()
                cluster_name = row['Cluster Name'].strip()
                site_name = row['Site Name'].strip()
                lat_str = row['Latitude'].strip()
                lon_str = row['Longitude'].strip()

                latitude = float(lat_str) if lat_str else None
                longitude = float(lon_str) if lon_str else None

                SiteData.objects.update_or_create(
                    global_id=global_id,
                    defaults={
                        'cluster_name': cluster_name,
                        'site_name': site_name,
                        'latitude': latitude,
                        'longitude': longitude
                    }
                )
                count += 1

        self.stdout.write(self.style.SUCCESS(f'Imported {count} site records successfully.'))
