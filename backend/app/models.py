from django.db import models
import uuid
from master.models import Plant, Product

class Challan(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    challan_number = models.CharField(max_length=50, unique=True)
    challan_date = models.DateField()
    
    from_plant = models.ForeignKey(Plant, on_delete=models.PROTECT, related_name="outgoing_challans")
    to_plant = models.ForeignKey(Plant, on_delete=models.PROTECT, related_name="incoming_challans")
    
    customer_name = models.CharField(max_length=255)
    customer_address = models.TextField(blank=True, null=True)
    customer_state = models.CharField(max_length=100, blank=True, null=True)
    customer_city = models.CharField(max_length=100, blank=True, null=True)
    customer_pincode = models.CharField(max_length=20, blank=True, null=True)
    customer_gstin = models.CharField(max_length=20, blank=True, null=True)
    
    vehicle_no = models.CharField(max_length=50, blank=True, null=True)
    order_ref = models.CharField(max_length=50, blank=True, null=True)
    docket_no = models.CharField(max_length=50, blank=True, null=True)
    reason_for_dc = models.TextField(blank=True, null=True)
    
    total_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.challan_number

class ChallanItem(models.Model):
    challan = models.ForeignKey(Challan, related_name="items", on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=12, decimal_places=2)
    rate = models.DecimalField(max_digits=12, decimal_places=2)
    amount = models.DecimalField(max_digits=15, decimal_places=2)

    def __str__(self):
        return f"{self.product.name} - {self.quantity}"