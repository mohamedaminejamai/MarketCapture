from django.db import models
from django.contrib.auth.models import User

class SearchLog(models.Model):
    url = models.URLField(max_length=1000)
    timestamp = models.DateTimeField(auto_now_add=True)
    results_found = models.IntegerField()

    def __str__(self):
        return f"Search at {self.timestamp}"

class SavedProduct(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    name = models.CharField(max_length=255)
    price = models.CharField(max_length=50)
    url = models.URLField(max_length=1000)
    image = models.URLField(max_length=1000, blank=True, null=True)
    source = models.CharField(max_length=50, blank=True, null=True)
    saved_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name