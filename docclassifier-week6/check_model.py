from app.classifier.model import verify_model_integrity, MIN_TOP1
import json

card = json.load(open('app/classifier/models/model_card.json'))
metrics = card.get('metrics', {})
top1 = metrics.get('test_top1', 0.0)

print(f"MIN_TOP1 constant    : {MIN_TOP1}")
print(f"Model test_top1      : {top1}")
print(f"Card min_threshold   : {card.get('min_top1_threshold', 'N/A')}")
print(f"Check will pass?     : {top1 >= MIN_TOP1}")
