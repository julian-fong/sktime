"""Adapter for using the huggingface PatchTST for forecasting."""

# documentation for PatchTST:
# https://huggingface.co/docs/transformers/main/en/model_doc/patchtst#transformers.PatchTSTConfig

import warnings
from copy import deepcopy

import numpy as np
import pandas as pd
from skbase.utils.dependencies import _check_soft_dependencies

from sktime.forecasting.base import ForecastingHorizon, _BaseGlobalForecaster
from sktime.split import temporal_train_test_split

if _check_soft_dependencies("torch", severity="none"):
    import torch
    from torch.utils.data import Dataset
else:

    class Dataset:
        """Dummy class if torch is unavailable."""

        pass


if _check_soft_dependencies("transformers", severity="none"):
    from transformers import (
        PatchTSTConfig,
        PatchTSTForPrediction,
        PatchTSTModel,
        Trainer,
        TrainingArguments,
    )


class HFPatchTSTForecaster(_BaseGlobalForecaster):
    """Interface for the PatchTST forecaster.

    This model has 3 available modes:
        1) Loading an full PatchTST model and pretrain on some dataset.
        This can be done by passing in a PatchTST config dictionary or passing
        in available parameters in this estimator, or by loading the
        HFPatchTSTForecaster without any passed arguments. See the
        `fit_strategy` docstring for more details.

        2) Load a pre-trained model for fine-tuning. Both the parameters `model_path`
        and `config` can be used to load a pre-trained model for fine-tuning and
        to re-initialize new weights in the pre-trained model using the config
        parameters if necessary. Use a passed in `y` and `fh` in the `fit`
        function to then fine-tune your pretrained model. See the
        `fit_strategy` docstring for more details.

        3) Load a pre-trained model for zero-shot forecasting. The parameter
        `model_path` can be used to load a pre-trained model and can be
        used immediately for forecasting via the `predict` function after
        passing a `y` and `fh` into `fit`. See the `fit_strategy` docstring
        for more details.

    Parameters
    ----------
    model_path : str, optional
        Path to the Huggingface model to use for global forecasting. If
        model_path is passed, the remaining model config parameters will be
        ignored except for specific training or dataset parameters.
        This has 3 options:
            - model id to an online pretrained PatchTST Model hosted on HuggingFace
            - A path or url to a saved configuration JSON file
            - A path to a *directory* containing a configuration file saved
            using the `~PretrainedConfig.save_pretrained` method
            or the `~PreTrainedModel.save_pretrained` method
    fit_strategy : str, values = ["full","minimal","zero-shot"], default = "full"
        String to set the fit_strategy of the model.

        - This strategy is used to create and train a new model from scratch
        (pre-pretraining) or to update all of the weights in a pre-trained model
        (also known as full fine-tuning). If `fit_strategy` is set to `full`,
        requires either the `model_path` parameter or the `config`` parameter
        to be passed in, but not both. If only `config` is passed, it will
        initialize an new model with untrained weights with the specified config
        arguments. If only `model_path` is passed, it will fine-tune ALL of the
        pre-trained weights of the model.

        - If `fit_strategy` is set to "minimal" requires both the `model_path`
        and `config` parameter. We will use the `model_path` and the specified
        `config` to compare the weight shapes of the passed pre-trained model
        to those in the config. If there are weight size mismatches, the model
        will reinitialize new weights to match the weight shapes inside the `config`.
        The `y` argument will then be fit to fine-tune the model. In the case where
        there are no newly initialized weights (i.e the config weight shapes match
        the pretrained model weight shapes), it will behave the same as the "full"
        strategy where only the `model_path` is passed in.

        - If `fit_strategy` is set to "zero-shot", requires only the `model_path`
        parameter. It will load the model via the `fit` function with the argument
        `model_path` and ignore any passed `y`.
    validation_split : float, optional, default = 0.2
        Fraction of the data to use for validation.
    config : dict, optional, default = {}
        A config dict specifying parameters to initialize an full
        PatchTST model. Missing parameters in the config will be automatically
        replaced by their default values. See the PatchTSTConfig config on
        huggingface for more details.
        Note: if `prediction_length` is passed as in larger than the passed `fh`
        in the `fit` function, the `prediction_length` will be used to train the
        model. If `prediction_length` is passed as in smaller than the passed
        `fh` in the `fit` function, the passed `fh` will be used to train the
        model.
    training_args : dict, optional, default = None
        Training arguments to use for the model. If this is passed,
        the remaining applicable training arguments will be ignored
    compute_metrics : list or function, default = None
        List of metrics or function to use during training
    callbacks: list or function, default = None
        List of callbacks or callback function to use during training

    References
    ----------
    Paper: https://arxiv.org/abs/2211.14730
    HuggingFace Page: https://huggingface.co/docs/transformers/en/model_doc/patchtst

    Examples
    --------
    >>> #Example with a new model initialized from config
    >>> from sktime.forecasting.hf_patchtst_forecaster import HFPatchTSTForecaster
    >>> from sktime.datasets import load_airline
    >>> y = load_airline()
    >>> forecaster = HFPatchTSTForecaster(
    ... config = {
    ...     "patch_length": 1,
    ...      "context_length": 2,
    ...      "patch_stride": 1,
    ...      "d_model": 64,
    ...      "num_attention_heads": 2,
    ...      "ffn_dim": 32,
    ...      "head_dropout": 0.3,
    ...    },
    ...    training_args = {
    ...         "output_dir":"/PatchTST/",
    ...         "overwrite_output_dir":True,
    ...         "learning_rate":1e-4,
    ...         "num_train_epochs":1,
    ...         "per_device_train_batch_size":16,
    ...    }
    ... ) #initialize an full model
    >>> forecaster.fit(y, fh=[1, 2, 3]) # doctest: +SKIP
    >>> y_pred = forecaster.predict() # doctest: +SKIP

    >>> #Example full fine-tuning with a pre-trained model
    >>> from sktime.forecasting.hf_patchtst_forecaster import HFPatchTSTForecaster
    >>> import pandas as pd
    >>> dataset_path = pd.read_csv(
    ...     "https://raw.githubusercontent.com/zhouhaoyi/ETDataset/main/ETT-small/ETTh1.csv"
    ...     ).drop(columns = ["date"]
    ... )
    >>> from sklearn.preprocessing import StandardScaler
    >>> scaler = StandardScaler()
    >>> scaler.set_output(transform="pandas") # doctest: +SKIP
    >>> scaler = scaler.fit(dataset_path.values) # doctest: +SKIP
    >>> df = scaler.transform(dataset_path) # doctest: +SKIP
    >>> df.columns = dataset_path.columns
    >>> forecaster = HFPatchTSTForecaster(
    ...     model_path="namctin/patchtst_etth1_forecast",
    ...     fit_strategy = "full",
    ...     training_args = {
    ...         "output_dir":"/PatchTST/",
    ...         "overwrite_output_dir":True,
    ...         "learning_rate":1e-4,
    ...         "num_train_epochs":1,
    ...         "per_device_train_batch_size":16,
    ...     }
    ... ) # doctest: +SKIP
    >>> forecaster.fit(y = df, fh = list(range(1,4))) # doctest: +SKIP
    >>> y_pred = forecaster.predict() # doctest: +SKIP

    >>> #Example of minimal fine-tuning with a pre-trained model
    >>> from sktime.forecasting.hf_patchtst_forecaster import HFPatchTSTForecaster
    >>> import pandas as pd
    >>> dataset_path = pd.read_csv(
    ...     "https://raw.githubusercontent.com/zhouhaoyi/ETDataset/main/ETT-small/ETTh1.csv"
    ...     ).drop(columns = ["date"]
    ... )
    >>> from sklearn.preprocessing import StandardScaler
    >>> scaler = StandardScaler()
    >>> scaler.set_output(transform="pandas") # doctest: +SKIP
    >>> scaler = scaler.fit(dataset_path.values) # doctest: +SKIP
    >>> df = scaler.transform(dataset_path) # doctest: +SKIP
    >>> df.columns = dataset_path.columns
    >>> forecaster = HFPatchTSTForecaster(
    ...     model_path="namctin/patchtst_etth1_forecast",
    ...     config = {
    ...         "patch_length": 8,
    ...         "context_length": 512,
    ...         "patch_stride": 8,
    ...         "d_model": 128,
    ...         "num_attention_heads": 2,
    ...         "ffn_dim": 512,
    ...         "head_dropout": 0.3,
    ...         "prediction_length": 64
    ...     },
    ...     fit_strategy = "minimal",
    ...     training_args = {
    ...         "output_dir":"/PatchTST/",
    ...         "overwrite_output_dir":True,
    ...         "learning_rate":1e-4,
    ...         "num_train_epochs":1,
    ...         "per_device_train_batch_size":16,
    ...     }
    ... ) # doctest: +SKIP
    >>> forecaster.fit(y = df, fh = list(range(1,63))) # doctest: +SKIP
    >>> y_pred = forecaster.predict() # doctest: +SKIP

    >>> #Example with a pre-trained model to do zero-shot forecasting
    >>> from sktime.forecasting.hf_patchtst_forecaster import HFPatchTSTForecaster
    >>> import pandas as pd
    >>> dataset_path = pd.read_csv(
    ...     "https://raw.githubusercontent.com/zhouhaoyi/ETDataset/main/ETT-small/ETTh1.csv"
    ...     ).drop(columns = ["date"]
    ... )
    >>> from sklearn.preprocessing import StandardScaler
    >>> scaler = StandardScaler()
    >>> scaler.set_output(transform="pandas") # doctest: +SKIP
    >>> scaler = scaler.fit(dataset_path.values) # doctest: +SKIP
    >>> df = scaler.transform(dataset_path) # doctest: +SKIP
    >>> df.columns = dataset_path.columns
    >>> forecaster = HFPatchTSTForecaster(
    ...     model_path="namctin/patchtst_etth1_forecast",
    ...     fit_strategy = "zero-shot",
    ...     training_args = {
    ...         "output_dir":"/PatchTST/",
    ...         "overwrite_output_dir":True,
    ...         "learning_rate":1e-4,
    ...         "num_train_epochs":1,
    ...         "per_device_train_batch_size":16,
    ...     }
    ... ) # doctest: +SKIP
    >>> forecaster.fit(y = df, fh = [1,2,3,4,5]) # doctest: +SKIP
    >>> y_pred = forecaster.predict() # doctest: +SKIP
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
        "requires-fh-in-fit": True,
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
        fit_strategy="full",
        validation_split=0.2,
        config=None,
        training_args=None,
        compute_metrics=None,
        callbacks=None,
    ):
        self.model_path = model_path
        self.fit_strategy = fit_strategy
        # dataset and training parameters
        self.validation_split = validation_split
        self.config = config
        self.training_args = training_args
        self._training_args = training_args if training_args is not None else {}
        self.compute_metrics = compute_metrics
        self.callbacks = callbacks

        self._config = deepcopy(self.config)
        super().__init__()
        if self.fit_strategy not in ["full", "minimal", "zero-shot"]:
            raise ValueError("unexpected fit_strategy passed in argument")

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
        self._y = y
        self.fh_ = int(max(fh.to_relative(self.cutoff)))
        self.y_columns = y.columns
        # if no model_path was given, initialize new full model from config
        if self.fit_strategy == "full":
            if not self.model_path:
                self._config["num_input_channels"] = len(self.y_columns)
                if "prediction_length" in self._config.keys():
                    if self._config["prediction_length"] > self.fh_:
                        warnings.warn(
                            "Found `prediction_length` inside config larger"
                            " than passed fh, will use larger of the two to"
                            " initalize the model"
                        )
                    elif self._config["prediction_length"] <= self.fh_:
                        warnings.warn(
                            "Found `fh` argument length larger"
                            " than passed prediction_length inside config"
                            " ,will use larger of the two to initialize the model"
                        )
                        self._config["prediction_length"] = int(self.fh_)
                else:
                    # if `prediction_length` isn't in the config, use the passed fh
                    self._config["prediction_length"] = int(self.fh_)
                # extract the context_length from the config
                # and pass back into the model config arguments due to some bug
                context_length = self._config["context_length"]
                del self._config["context_length"]
                config = PatchTSTConfig(
                    context_length=context_length,
                    **self._config,
                )
                self.model = PatchTSTForPrediction(config)
            elif not self.config:
                self.model = PatchTSTForPrediction.from_pretrained(self.model_path)
            else:
                raise ValueError(
                    "fit_strategy = 'full' requires either `model_path` or `config`"
                    " but not both."
                )
        elif self.fit_strategy == "minimal":
            if not self.model_path or not self.config:
                raise ValueError(
                    "fit_strategy = 'minimal' requires both model_path and config"
                )
            else:
                self._config["num_input_channels"] = len(self.y_columns)
                if "prediction_length" in self._config.keys():
                    if self._config["prediction_length"] > self.fh_:
                        warnings.warn(
                            "Found `prediction_length` inside config larger"
                            " than passed fh, will use larger of the two to"
                            " initalize the model"
                        )
                    elif self._config["prediction_length"] <= self.fh_:
                        warnings.warn(
                            "Found `fh` argument length larger"
                            " than passed prediction_length inside config"
                            " ,will use larger of the two to initialize the model"
                        )
                        self._config["prediction_length"] = int(self.fh_)
                else:
                    # if `prediction_length` isn't in the config, use the passed fh
                    self._config["prediction_length"] = int(self.fh_)
                # extract the context_length from the config
                # and pass back into the model config arguments due to some bug
                context_length = self._config["context_length"]
                del self._config["context_length"]
                config = PatchTSTConfig(
                    context_length=context_length,
                    **self._config,
                )

                # Load model with the updated config
                self.model, info = PatchTSTForPrediction.from_pretrained(
                    self.model_path,
                    config=config,
                    output_loading_info=True,
                    ignore_mismatched_sizes=True,
                )

                # Freeze all loaded parameters
                for param in self.model.parameters():
                    param.requires_grad = False

                # Clamp all loaded parameters to avoid NaNs due to large values
                for param in self.model.model.parameters():
                    param.clamp_(-1000, 1000)

                # Reininit the weights of all layers that have mismatched sizes
                for key, _, _ in info["mismatched_keys"]:
                    _model = self.model
                    for attr_name in key.split(".")[:-1]:
                        _model = getattr(_model, attr_name)
                    if hasattr(_model, "weight"):
                        _model.weight = torch.nn.Parameter(
                            _model.weight.masked_fill(_model.weight.isnan(), 0.001),
                            requires_grad=True,
                        )
                    elif hasattr(_model, "position_enc"):
                        torch.nn.init.normal_(_model.position_enc, mean=0.0, std=0.1)
                        _model.position_enc.requires_grad = True

        elif self.fit_strategy == "zero-shot":
            self.model = PatchTSTForPrediction.from_pretrained(self.model_path)
            if not isinstance(self.model.model, PatchTSTModel):
                raise ValueError(
                    "This estimator requires a `PatchTSTModel`, but "
                    f"found {self.model.model.__class__.__name__}"
                )
        # only train the model if the fit_strategy is full or minimal
        if self.fit_strategy == "full" or self.fit_strategy == "minimal":
            # initialize dataset
            y_train, y_test = temporal_train_test_split(
                y, train_size=1 - self.validation_split, test_size=self.validation_split
            )
            train_dataset = PyTorchDataset(
                y_train,
                context_length=self.model.config.context_length,
                prediction_length=self.model.config.prediction_length,
            )
            if self.validation_split > 0.0:
                eval_dataset = PyTorchDataset(
                    y_test,
                    context_length=self.model.config.context_length,
                    prediction_length=self.model.config.prediction_length,
                )
            else:
                eval_dataset = None

            # initialize training_args
            training_args = TrainingArguments(**self._training_args)

            trainer = Trainer(
                model=self.model,
                args=training_args,
                train_dataset=train_dataset,
                eval_dataset=eval_dataset,
                callbacks=self.callbacks,
                compute_metrics=self.compute_metrics,
            )

            trainer.train()

        return self

    def _predict(self, y, X=None, fh=None):
        """Forecast time series at future horizon.

        private _predict containing the core logic, called from predict

        State required:
            Requires state to be "fitted".

        Accesses in self:
            Fitted model attributes ending in "_"
            self.cutoff

        Parameters
        ----------
        fh : guaranteed to be ForecastingHorizon or None, optional (default=None)
            The forecasting horizon with the steps ahead to to predict.
            If not passed in _fit, guaranteed to be passed here. If using a pre-trained
            model, ensure that the prediction_length of the model matches the passed fh.
        y : sktime time series object, required
            single or multivariate data to compute forecasts on.

        Returns
        -------
        y_pred : sktime time series object
            pandas DataFrame
        """
        if y is None:
            y = self._y
        if fh is None:
            fh = self.fh_
        else:
            fh = fh.to_relative(self.cutoff)
        y_columns = y.columns
        y_index_names = list(y.index.names)
        # multi-index conversion
        if isinstance(y.index, pd.MultiIndex):
            _y = _frame2numpy(y)
        else:
            _y = np.expand_dims(y.values, axis=0)

        _y = torch.tensor(_y).float().to(self.model.device)

        if _y.shape[1] > self.model.config.context_length:
            _y = _y[:, -self.model.config.context_length :, :]

        # in the case where the context_length of the pre-trained model is larger
        # than the context_length of the model
        self.model.eval()
        y_pred = self.model(_y).prediction_outputs
        pred = y_pred.detach().cpu().numpy()

        if isinstance(y.index, pd.MultiIndex):
            ins = np.array(list(np.unique(y.index.droplevel(-1)).repeat(pred.shape[1])))
            ins = [ins[..., i] for i in range(ins.shape[-1])] if ins.ndim > 1 else [ins]

            idx = (
                ForecastingHorizon(range(1, pred.shape[1] + 1), freq=self.fh.freq)
                .to_absolute(self._cutoff)
                ._values.tolist()
                * pred.shape[0]
            )
            index = pd.MultiIndex.from_arrays(
                ins + [idx],
                names=y.index.names,
            )
        else:
            index = (
                ForecastingHorizon(range(1, pred.shape[1] + 1))
                .to_absolute(self._cutoff)
                ._values
            )

        df_pred = pd.DataFrame(
            # batch_size * num_timestams, n_cols
            pred.reshape(-1, pred.shape[-1]),
            index=index,
            columns=y_columns,
        )

        absolute_horizons = fh.to_absolute_index(self.cutoff)
        dateindex = df_pred.index.get_level_values(-1).map(
            lambda x: x in absolute_horizons
        )
        df_pred = df_pred.loc[dateindex]
        df_pred.index.names = y_index_names
        return df_pred

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
            "config": {
                "patch_length": 2,
                "context_length": 4,
                "patch_stride": 2,
                "d_model": 32,
                "num_attention_heads": 1,
                "ffn_dim": 16,
                "head_dropout": 0.3,
            },
            "training_args": {
                "output_dir": "/PatchTST/",
                "overwrite_output_dir": True,
                "learning_rate": 1e-4,
                "num_train_epochs": 1,
                "per_device_train_batch_size": 16,
            },
            "validation_split": 0.0,
        }
        params_set.append(params1)
        params2 = {
            "config": {
                "patch_length": 1,
                "context_length": 2,
                "patch_stride": 1,
                "d_model": 64,
                "num_attention_heads": 2,
                "ffn_dim": 32,
                "head_dropout": 0.3,
            },
            "training_args": {
                "output_dir": "/PatchTST/",
                "overwrite_output_dir": True,
                "learning_rate": 1e-4,
                "num_train_epochs": 1,
                "per_device_train_batch_size": 16,
            },
            "validation_split": 0.0,
        }
        params_set.append(params2)

        return params_set


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
