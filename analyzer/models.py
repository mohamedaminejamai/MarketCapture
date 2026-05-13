from django.db import models

class SearchLog(models.Model):
    url = models.URLField(max_length=1000)
    timestamp = models.DateTimeField(auto_now_add=True)
    results_found = models.IntegerField()

    def __str__(self):
        return f"Search at {self.timestamp}"