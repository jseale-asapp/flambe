from typing import Optional

import torch

from flambe.compile import Component
from flambe.dataset import Dataset
from flambe.nn import Module
from flambe.metric import Metric
from flambe.sampler import Sampler, BaseSampler
from flambe.logging import log


class Evaluator(Component):
    """Implement an Evaluator block.

    An `Evaluator` takes as input data, and a model and executes
    the evaluation. This is a single step `Component` object.

    """

    def __init__(self,
                 dataset: Dataset,
                 model: Module,
                 metric_fn: Metric,
                 eval_sampler: Optional[Sampler] = None,
                 eval_data: str = 'test',
                 device: Optional[str] = None) -> None:
        """Initialize the evaluator.

        Parameters
        ----------
        dataset : Dataset
            The dataset to run evaluation on
        model : Module
            The model to train
        metric_fn: Metric
            The metric to use for evaluation
        eval_sampler : Optional[Sampler]
            The sampler to use over validation examples. By default
            it will use `BaseSampler` with batch size 16 and without
            shuffling.
        eval_data: str
            The data split to evaluate on: one of train, val or test
        device: str, optional
            The device to use in the computation.

        """
        self.eval_sampler = eval_sampler or BaseSampler(batch_size=16, shuffle=False)
        self.model = model
        self.metric_fn = metric_fn
        self.eval_metric = None
        self.dataset = dataset

        # Select right device
        if device is not None:
            self.device = device
        else:
            self.device = "cuda" if torch.cuda.is_available() else "cpu"

        data = getattr(dataset, eval_data)
        self._eval_iterator = self.eval_sampler.sample(data)

        # By default, no prefix applied to tb logs
        self.tb_log_prefix = None

    def run(self, block_name: str = None) -> bool:
        """Run the evaluation.

        Returns
        ------
        bool
            Whether the component should continue running.

        """
        self.model.to(self.device)
        self.model.eval()
        with torch.no_grad():
            preds, targets = [], []

            for batch in self._eval_iterator:
                pred, target = self.model(*[t.to(self.device) for t in batch])
                preds.append(pred.cpu())
                targets.append(target.cpu())

            preds = torch.cat(preds, dim=0)  # type: ignore
            targets = torch.cat(targets, dim=0)  # type: ignore
            self.eval_metric = self.metric_fn(preds, targets).item()

            tb_prefix = f"{self.tb_log_prefix} " if self.tb_log_prefix else ""

            log(f'{tb_prefix}Eval {self.metric_fn}',  # type: ignore
                self.eval_metric, global_step=0)  # type: ignore

        continue_ = False  # Single step so don't continue
        return continue_

    def metric(self) -> Optional[float]:
        """Override this method to enable scheduling.

        Returns
        -------
        float
            The metric to compare computable varients

        """
        return self.eval_metric
