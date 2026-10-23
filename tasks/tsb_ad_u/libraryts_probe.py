"""Synthetic compatibility probe; this is not a benchmark candidate or baseline."""
import numpy as np

def detect(data, train_data, metadata):
    import pandas as pd
    import torch
    from pyod.models.ecod import ECOD
    from sktime.detection.adapters import PyODDetector
    from sktime.detection.compose import DetectorPipeline
    from sktime.transformations.series.adapt import TabularToSeriesAdaptor
    from sklearn.preprocessing import StandardScaler
    from sktime.forecasting.naive import NaiveForecaster
    from sktime.detection.skchange_aseg import CAPA
    from sktime.detection.skchange_cp import MovingWindow, PELT
    from hmmlearn.hmm import GaussianHMM
    import sktime
    from pathlib import Path
    assert not (Path(sktime.__file__).parent / "datasets/data").exists()
    x = pd.DataFrame(data)
    model = PyODDetector(ECOD(n_jobs=1)).fit(x)
    scores = model.estimator_.decision_function(x.to_numpy())
    assert len(scores) == len(data)
    pipeline = DetectorPipeline(steps=[("scale", TabularToSeriesAdaptor(StandardScaler())),
                                      ("detector", PyODDetector(ECOD(n_jobs=1)))])
    pipeline.fit(x)
    pipeline.predict(x)
    for detector in (CAPA(), MovingWindow(bandwidth=5), PELT()):
        detector.fit_predict(x)
    hmm = GaussianHMM(n_components=2, n_iter=3, random_state=2024).fit(data)
    assert np.isfinite(hmm.score(data))
    forecast = NaiveForecaster(strategy="last").fit(pd.Series(train_data[:,0])).predict([1,2])
    assert np.isfinite(forecast).all()
    t = torch.tensor([1.,2.], device=metadata["device"])
    assert float((t*t).sum().cpu()) == 5.
    return scores
