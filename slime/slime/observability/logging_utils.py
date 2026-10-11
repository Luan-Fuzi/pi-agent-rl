import logging
import os

import wandb

from slime.observability import wandb_utils
from slime.observability.tensorboard_utils import _TensorboardAdapter

_LOGGER_CONFIGURED = False
_SWANLAB_WARNED = False


def _swanlab_log(metrics, step_key: str):
    """Mirror metrics to the active SwanLab run; failures never break training."""
    global _SWANLAB_WARNED
    if os.environ.get("SLIME_SWANLAB_SYNC") != "1":
        return
    try:
        import swanlab

        # NOTE: swanlab.get_run() raises when no run is active; has_run() does not.
        if swanlab.has_run():
            step = metrics.get(step_key)
            swanlab.log(metrics, step=int(step) if isinstance(step, (int, float)) else None)
    except Exception:
        if not _SWANLAB_WARNED:
            _SWANLAB_WARNED = True
            logging.getLogger(__name__).exception("SwanLab log failed; further SwanLab errors suppressed")


# ref: SGLang
def configure_logger(prefix: str = ""):
    global _LOGGER_CONFIGURED
    if _LOGGER_CONFIGURED:
        return

    _LOGGER_CONFIGURED = True

    logging.basicConfig(
        level=logging.INFO,
        format=f"[%(asctime)s{prefix}] %(filename)s:%(lineno)d - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        force=True,
    )


def init_tracking(args, primary: bool = True, **kwargs):
    if primary:
        wandb_utils.init_wandb_primary(args, **kwargs)
    else:
        wandb_utils.init_wandb_secondary(args, **kwargs)


def finish_tracking(args):
    if not args.use_wandb:
        return
    try:
        if wandb.run is not None:
            wandb.finish()
    except Exception:
        logging.getLogger(__name__).exception("Failed to finish wandb run")
    if os.environ.get("SLIME_SWANLAB_SYNC") == "1":
        try:
            import swanlab

            if swanlab.has_run():
                swanlab.finish()
        except Exception:
            logging.getLogger(__name__).exception("Failed to finish SwanLab run")


# TODO further refactor, e.g. put TensorBoard init to the "init" part
def log(args, metrics, step_key: str):
    if args.use_wandb:
        wandb.log(metrics)
        _swanlab_log(metrics, step_key)

    if args.use_tensorboard:
        metrics_except_step = {k: v for k, v in metrics.items() if k != step_key}
        _TensorboardAdapter(args).log(data=metrics_except_step, step=metrics[step_key])
