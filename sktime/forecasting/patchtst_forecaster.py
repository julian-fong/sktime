"""Adapter for using the huggingface PatchTST for forecasting."""

# documentation for PatchTST:
# https://huggingface.co/docs/transformers/main/en/model_doc/patchtst#transformers.PatchTSTConfig

import numpy as np
import pandas as pd
from skbase.utils.dependencies import _check_soft_dependencies
from transformers import (
    PatchTSTConfig,
    PatchTSTForPrediction,
    PatchTSTModel,
    Trainer,
    TrainingArguments,
)

from sktime.forecasting.base import _BaseGlobalForecaster
from sktime.split import temporal_train_test_split

if _check_soft_dependencies(["torch"], severity="none"):
    from torch.utils.data import Dataset
else:

    class Dataset:
        """Dummy class if torch is unavailable."""

        pass


class HFPatchTSTForecaster(_BaseGlobalForecaster):
    """Interface for the PatchTST forecaster.

    Paper: https://arxiv.org/abs/2211.14730

    This model has 3 available modes:
        1) Loading an untrained PatchTST model and pretrain on some dataset.
        This can be done by passing in a PatchTST config dictionary or passing
        in available parameters in this estimator, or by loading the
        HFPatchTSTForecaster without any passed arguments
        2) Load a pre-trained model for fine-tuning. The parameter `model_path`
        can be load to load a pre-trained model for fine-tuning. Using a
        pretrained model will override any other model config parameters, and
        you can use the `fit` function to then fine-tune your pretrained model.
        See the `model_path` docstring for more details.
        3) Load a pre-trained model for zero-shot forecasting. The parameter
        `model_path` can be load to load a pre-trained model for fine-tuning.
        Using a pretrained model will override any other model config
        parameters, and you can use the `predict` function to do zero-shot
        forecasting. See the `model_path` docstring for more details.

    Parameters
    ----------
    model_path : str, optional
        Path to the Huggingface model to use for global forecasting. If
        model_path is passed, the remaining model config parameters will be
        ignored except for specific training or dataset parameters.
        This has 3 options:
            - model id to an online pretrained PatchTST Model hosted on HuggingFace
            - A path to a *directory* containing a configuration file saved
            using the [`~PretrainedConfig.save_pretrained`] method,
            or the [`~PreTrainedModel.save_pretrained`] method
            - A path or url to a saved configuration JSON *file*, e.g.,
                `./my_model_directory/configuration.json`.
            forecast_columns,
    mode : str, optional, possible values = ["untrained", "finetune", "zeroshot"]
           default = "untrained"
        String to set the mode of the model. If set to 'untrained', it will
        re-initialize an untrained model with the specified config or
        estimator aruguments. If set to "finetune" will use the `model_path`
        argument and the passed in `y` in fit to fine-tune the model. If
        set to "zeroshot", it will load the model in zero-shot forecasting
        model with the argument `model_path` and ignore any passed `y`.
        Note that both "finetune" and "zeroshot" mode requires a mandatory
        passed in `model_path`.
    patch_length : int, optional, default = 4
        Length of each patch that will segment every univariate series.
    context_length : int, optional, default = 3
        Number of previous time steps used to forecast.
    patch_stride : int, optional, default = 4
        Length of the non-overlapping region between patches. If patch_stride
        is less than patch_length, then there will be overlapping patches. If
        patch_stride = patch_length, then there will be no overlapping patches.
    random_mask_ratio : float, optional, default = 0.4
        Masking ratio applied to mask the input data during random pretraining.
    d_model : int, optional, default = 128
        Dimension of the weight matrices in the transformer layers.
    num_attention_heads : int, optional, default = 16
        Number of attention heads for each attention layer in the transformer block
    ffn_dim : int, optional, default = 256
        Dimensionality of the feed forward layer in the transformer encoder.
    head_dropout : float, optional, default = 0.2
        Dropout probability for a head.
    batch_size : int, optional, default = 64
        Size of every batch during training. Reduce if you have reduced gpu power.
    learning_rate : float, optional, default = 1e-4
        Leaning rate that is used during training.
    epochs : int, optional, default = 10
        Number of epochs to use during training.
    validation_split : float, optional, default = 0.2
        Fraction of the data to use for validation.
    config : dict, optional, default = {}
        A config dict specifying parameters to initialize an untrained
        PatchTST model. Missing parameters in the config will be automatically
        replaced by their default values. See the PatchTSTConfig config on
        huggingface for more details.
    training_args : dict, optional, default = None
        Training arguments to use for the model. If this is passed,
        the remaining applicable training arguments will be ignored
    compute_metrics : list or function, default = None
        List of metrics or function to use to use during training
    callbacks: list or function, default = None
        List of callbacks or callback function to use during training
    broadcasting : bool, default=False
        if True, multiindex data input will be broadcasted to single series.
        For each single series, one copy of this forecaster will try to
        fit and predict on it. The broadcasting is happening inside automatically,
        from the outerside api perspective, the input and output are the same,
        only one multiindex output from ``predict``.


    """

    _tags = {
        "X_inner_mtype": [
            "pd.DataFrame",
            "pd-multiindex",
            "pd_multiindex_hier",
        ],
        "y_inner_mtype": [
            "pd.DataFrame",
            "pd-multiindex",
            "pd_multiindex_hier",
        ],
        "scitype:y": "both",
        "ignores-exogeneous-X": True,
        "requires-fh-in-fit": False,
        "X-y-must-have-same-index": True,
        "enforce_index_type": None,
        "handles-missing-data": False,
        "capability:insample": False,
        "capability:pred_int": False,
        "capability:pred_int:insample": False,
        "authors": ["julian-fong"],
        "maintainers": ["julian-fong"],
        "python_dependencies": ["transformers", "torch"],
        "capability:global_forecasting": True,
    }

    def __init__(
        self,
        # model variables except for forecast_columns
        model_path=None,
        mode="untrained",
        patch_length=4,
        context_length=3,
        patch_stride=4,
        random_mask_ratio=0.4,
        d_model=128,
        num_attention_heads=16,
        ffn_dim=256,
        head_dropout=0.2,
        # dataset and training config
        batch_size=64,
        learning_rate=1e-4,
        epochs=10,
        validation_split=0.2,
        config=None,
        training_args=None,
        compute_metrics=None,
        callbacks=None,
        broadcasting=False,
    ):
        self.model_path = model_path
        self.mode = mode
        # model config parameters
        self.patch_length = patch_length
        self.context_length = context_length
        self.patch_stride = patch_stride
        self.random_mask_ratio = random_mask_ratio
        self.d_model = d_model
        self.num_attention_heads = num_attention_heads
        self.ffn_dim = ffn_dim
        self.head_dropout = head_dropout

        # dataset and training parameters
        self.batch_size = batch_size
        self.learning_rate = learning_rate
        self.epochs = epochs
        self.validation_split = validation_split
        self.config = config
        self._config = self.config if self.config else {}
        self.training_args = training_args
        self.compute_metrics = compute_metrics
        self.callbacks = callbacks
        self.broadcasting = broadcasting
        super().__init__()
        if self.mode not in ["untrained", "finetune", "zeroshot"]:
            raise ValueError("unexpected mode passed in argument")

        if not self._config:
            self.config["patch_length"] = self.patch_length
            self.config["context_length"] = self.context_length
            self.config["patch_stride"] = self.patch_stride
            self.config["random_mask_ratio"] = self.random_mask_ratio
            self.config["d_model"] = self.d_model
            self.config["num_attention_heads"] = self.num_attention_heads
            self.config["ffn_dim"] = self.ffn_dim
            self.config["head_dropout"] = self.head_dropout

    def _fit(self, y, fh, X=None):
        """Fits the model.

        Parameters
        ----------
        y : pandas DataFrame
            pandas dataframe containing single or multivariate data

        fh : Forecasting Horizon object
            used to determine forecasting horizon for predictions

        Returns
        -------
        self : a reference to the object
        """
        self.fh = max(fh.to_relative(self.cutoff))
        self.y_columns = y.columns
        self._config["num_input_channels"] = len(self.y_columns)
        self._config["prediction_length"] = self.fh
        # if no model_path was given, initialize new untrained model from config
        if not self.model_path:
            config = PatchTSTConfig(self._config)
            self.model = PatchTSTForPrediction(config)
        else:
            # model_path was given, initialize with model_path
            self.model = PatchTSTForPrediction.from_pretrained(self.model_path)
            if not isinstance(self.model.model, PatchTSTModel):
                raise ValueError(
                    "This estimator requires a `PatchTSTModel`, but "
                    f"found {self.model.model.__class__.__name__}"
                )

        if self.mode != "zeroshot":
            # initialize dataset
            y_train, y_test = temporal_train_test_split(
                y, train_size=1 - self.validation_split, test_size=self.validation_split
            )
            train_dataset = PyTorchDataset(
                y_train, context_length=self.context_length, prediction_length=self.fh
            )
            eval_dataset = PyTorchDataset(
                y_test, context_length=self.context_length, prediction_length=self.fh
            )

            # initialize training_args
            if self.training_args:
                training_args = TrainingArguments(self.training_args)
            else:
                training_args = TrainingArguments(
                    output_dir="/PatchTST/",
                    overwrite_output_dir=True,
                    learning_rate=self.learning_rate,
                    num_train_epochs=self.epochs,
                    evaluation_strategy="epoch",
                    per_device_train_batch_size=self.batch_size,
                    label_names=["future_values"],
                )

            # Create the early stopping callback

            # define trainer
            trainer = Trainer(
                model=self.model,
                args=training_args,
                train_dataset=train_dataset,
                eval_dataset=eval_dataset,
                callbacks=self.callbacks,
                compute_metrics=self.compute_metrics,
            )
            # pretrain
            trainer.train()
            self._fitted_model = trainer.model
        else:
            self._fitted_model = self.model

        return self

    def _predict(self, y, X=None, fh=None):
        # fh : pd.Index, pd.TimedeltaIndex, np.array, list, pd.Timedelta, or int
        """Predicts the model.

        Parameters
        ----------
        X : pandas DataFrame
            dataframe containing all the time series, univariate,
            multivariate acceptable

        y : pandas DataFrame, default = None
            pandas dataframe containing forecasted horizon to predict
            default None

        fh : Forecasting Horizon object
            used to determine forecasting horizon for predictions
            expected to be the same as the one used in _fit

        Returns
        -------
        y_pred : predictions outputted from the fitted model
        """
        y_pred = self.model(y)
        return y_pred

    @classmethod
    def get_test_params(cls, parameter_set="default"):
        """Return testing parameter settings for the estimator.

        Parameters
        ----------
        parameter_set : str, default="default"
            Name of the set of test parameters to return, for use in tests. If no
            special parameters are defined for a value, will return `"default"` set.

        Returns
        -------
        params : dict or list of dict, default = {}
            Parameters to create testing instances of the class
            Each dict are parameters to construct an "interesting" test instance, i.e.,
            `MyClass(**params)` or `MyClass(**params[i])` creates a valid test instance.
            `create_test_instance` uses the first (or only) dictionary in `params`
        """
        params_set = []
        params1 = {
            "random_mask_ratio": 0.4,
            "d_model": 64,
            "num_attention_heads": 4,
            "num_hidden_layers": 1,
            "ffn_dim": 32,
            "head_dropout": 0.2,
            "pooling_type": None,
            "channel_attention": False,
            "scaling": "std",
            "loss": "mse",
            "pre_norm": True,
            "norm_type": "batchnorm",
            "batch_size": 16,
            "epochs": 1,
        }
        params_set.append(params1)
        params2 = {
            "d_model": 128,
            "num_attention_heads": 4,
            "num_hidden_layers": 1,
            "ffn_dim": 32,
            "head_dropout": 0.2,
            "batch_size": 16,
            "epochs": 1,
        }
        params_set.append(params2)

        return params_set


from torch.utils.data import Dataset


def _same_index(data):
    data = data.groupby(level=list(range(len(data.index.levels) - 1))).apply(
        lambda x: x.index.get_level_values(-1)
    )
    assert data.map(
        lambda x: x.equals(data.iloc[0])
    ).all(), "All series must has the same index"
    return data.iloc[0], len(data.iloc[0])


def _frame2numpy(data):
    idx, length = _same_index(data)
    arr = np.array(data.values, dtype=np.float32).reshape(
        (-1, length, len(data.columns))
    )
    return arr


class PyTorchDataset(Dataset):
    """Dataset for use in sktime deep learning forecasters."""

    def __init__(self, y, context_length, prediction_length):
        """
        Initialize the dataset.

        Parameters
        ----------
        y : ndarray
            The time series data, shape (n_sequences, n_timestamps, n_dims)
        context_length : int
            The length of the past values
        prediction_length : int
            The length of the future values
        """
        self.context_length = context_length
        self.prediction_length = prediction_length

        # multi-index conversion
        if isinstance(y.index, pd.MultiIndex):
            self.y = _frame2numpy(y)
        else:
            self.y = np.expand_dims(y.values, axis=0)

        self.n_sequences, self.n_timestamps, _ = self.y.shape
        self.single_length = (
            self.n_timestamps - self.context_length - self.prediction_length + 1
        )

    def __len__(self):
        """Return the length of the dataset."""
        # Calculate the number of samples that can be created from each sequence
        return self.single_length * self.n_sequences

    def __getitem__(self, i):
        """Return data point."""
        from torch import tensor

        m = i % self.single_length
        n = i // self.single_length

        past_values = self.y[n, m : m + self.context_length, :]
        future_values = self.y[
            n,
            m + self.context_length : m + self.context_length + self.prediction_length,
            :,
        ]

        return {
            "past_values": tensor(past_values).float(),
            "future_values": tensor(future_values).float(),
        }
