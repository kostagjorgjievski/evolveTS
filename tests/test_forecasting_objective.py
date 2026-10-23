import importlib.util,json
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('gift_v2_objective',ROOT/'tasks/gift_forecasting_v2/evaluator.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

def test_crps_only_objective_ignores_mase():
    ref={'a':{'eval_metrics/mean_weighted_sum_quantile_loss':2.,'eval_metrics/MASE[0.5]':1.}}
    def result(mase):
        return module.relative_scores([{'dataset':'a','eval_metrics/mean_weighted_sum_quantile_loss':1.,'eval_metrics/MASE[0.5]':mase}],ref)
    assert result(1.)['weighted_relative']==pytest.approx(.5)
    assert result(100.)['weighted_relative']==pytest.approx(.5)

def test_checkpoint_path_is_checkout_local():
    assert Path(module.PROTOCOL['models_host_dir'])==ROOT/'checkpoints'

def test_objective_weights_are_crps_only():
    assert module.PROTOCOL['objective_weights']=={'crps':1.0,'mase':0.0}
