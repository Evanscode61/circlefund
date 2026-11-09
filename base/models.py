import uuid

from django.db import models

class BaseModel(models.Model):
    """Define repetitive fields"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False,max_length=100)
    date_created = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class GenericBaseModel(BaseModel):
    """Define repetitive fields"""
    name = models.CharField(max_length=200)
    description = models.TextField(max_length=255, blank=True, null=True)

    class Meta(object):
        abstract = True
