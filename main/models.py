from django.db import models
from django.utils.timezone import now
from django.contrib.auth.models import User
from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.db.models import Sum
from django.utils.timezone import datetime
#Create your models here.
SELECT_CATEGORY_CHOICES = [
    ("Kitchen Food","Kitchen Food"),
    ("Petrol","Petrol"),
    ("item purchasing","item purchasing"),
    ("Necessities","Necessities"),
    ("Other","Other")
 ]

# PICK = [
#      ("Bill","Bill"),
#      ("No Bill","No Bill")
#  ]

    # PAID = [
    #     ('paid','paid'),
    #     ('not paid','not paid')
    # ]

class Post(models.Model):
    user = models.ForeignKey(User,default = 1, on_delete=models.CASCADE)
    category = models.CharField( max_length = 200, choices = SELECT_CATEGORY_CHOICES , default ='Food',null=True)
    # title = models.CharField(max_length=150,null=True)
    amount_taken = models.BigIntegerField()
    amount_used = models.BigIntegerField()
    
    date = models.DateField(default = now,null=True)
    desc = models.TextField(null=True)
    # bill = models.CharField(max_length=100,choices=PICK)
    bill = models.BooleanField(default=False)
    remaining = models.BooleanField(default=False)
    status = models.BooleanField(default=True)
    # status = 
    class Meta:
        db_table:'addmoney'
    @property
    def to_be_returned(self):
        return self.amount_taken - self.amount_used