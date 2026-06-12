from rest_framework import serializers
from .models import Challan, ChallanItem
from decimal import Decimal

class ChallanItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChallanItem
        fields = "__all__"
        extra_kwargs = {'challan': {'required': False}}

class ChallanSerializer(serializers.ModelSerializer):
    items = ChallanItemSerializer(many=True)

    class Meta:
        model = Challan
        fields = "__all__"
        read_only_fields = ('total_amount', 'challan_number')

    def create(self, validated_data):
        items_data = validated_data.pop("items")
        
        # Logic for auto-generating challan number could go here or in model save()
        # For now, we'll assume it's passed or handled via default
        if 'challan_number' not in validated_data:
             # Example logic mirroring your FastAPI 'SSPL' logic
             last_dc = Challan.objects.filter(challan_number__startswith='SSPL').order_by('challan_number').last()
             # ... increment logic ...
             validated_data['challan_number'] = "SSPL-TEMP-AUTO" 

        challan = Challan.objects.create(**validated_data)
        total = Decimal('0.00')

        for item in items_data:
            item_amount = Decimal(str(item["quantity"])) * Decimal(str(item["rate"]))
            total += item_amount
            ChallanItem.objects.create(challan=challan, amount=item_amount, **item)

        challan.total_amount = total
        challan.save()
        return challan