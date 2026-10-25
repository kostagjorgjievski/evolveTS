"""Task-specific acceptance of full DFTHC-SOS validation receipts."""
import math

def validate_receipt(receipt,level):
    official=receipt.get('official',{});validation=receipt.get('validation',{})
    cost=official.get('score')
    if (receipt.get('scope') not in ('full-development','full-local-final') or
            official.get('status')!='PASS' or validation.get('shots_per_address')!=64 or
            validation.get('metric_preflight') is not True or
            not validation.get('expected_shots') or official.get('verified_shots')!=validation['expected_shots'] or
            isinstance(cost,bool) or not isinstance(cost,(float,int)) or not math.isfinite(cost) or cost<=0):
        raise ValueError('Full unchanged DFTHC-SOS verification with metric preflight required')
    if level=='independently_verified' and not receipt.get('held_out'):
        raise ValueError('Independent verification requires a fresh-salt receipt')
