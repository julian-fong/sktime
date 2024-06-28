"""Tests for pairwise transformer."""

import numpy as np

__author__ = ["fkiraly"]

from sktime.tests.test_all_estimators import BaseFixtureGenerator, QuickTester


class TransformerPairwiseFixtureGenerator(BaseFixtureGenerator):
    """Fixture generator for pairwise transformer tests.

    Fixtures parameterized
    ----------------------
    estimator_class: estimator inheriting from BaseObject
        ranges over estimator classes not excluded by EXCLUDE_ESTIMATORS, EXCLUDED_TESTS
    estimator_instance: instance of estimator inheriting from BaseObject
        ranges over estimator classes not excluded by EXCLUDE_ESTIMATORS, EXCLUDED_TESTS
        instances are generated by create_test_instance class method
    scenario: instance of TestScenario
        ranges over all scenarios returned by retrieve_scenarios
    """

    estimator_type_filter = "transformer-pairwise"


class TestAllPairwiseTransformers(TransformerPairwiseFixtureGenerator, QuickTester):
    """Module level tests for all sktime pairwise transformers (tabular)."""

    def test_pairwise_transformers_tabular(self, estimator_instance, scenario):
        """Main test function for pairwise transformers on tabular data."""
        trafo_name = type(estimator_instance).__name__
        dist_mat = scenario.run(estimator_instance, method_sequence=["transform"])

        X = scenario.args["transform"]["X"]
        len_X = len(scenario.args["transform"]["X"])
        X2 = scenario.args["transform"].get("X2", X)
        len_X2 = len(X2)

        assert isinstance(
            dist_mat, np.ndarray
        ), f"Type of matrix returned by transform is wrong for {trafo_name}"
        assert (
            # this is only true as long as fixture are of mtypes where len = n_instances
            # should that change, use check_is_mtype to get n_instances metadata
            dist_mat.shape
            == (len_X, len_X2)
        ), f"Shape of matrix returned by transform is wrong for {trafo_name}"


class TransformerPairwisePanelFixtureGenerator(BaseFixtureGenerator):
    """Fixture generator for pairwise panel transformer tests.

    Fixtures parameterized
    ----------------------
    estimator_class: estimator inheriting from BaseObject
        ranges over estimator classes not excluded by EXCLUDE_ESTIMATORS, EXCLUDED_TESTS
    estimator_instance: instance of estimator inheriting from BaseObject
        ranges over estimator classes not excluded by EXCLUDE_ESTIMATORS, EXCLUDED_TESTS
        instances are generated by create_test_instance class method
    scenario: instance of TestScenario
        ranges over all scenarios returned by retrieve_scenarios
    """

    estimator_type_filter = "transformer-pairwise-panel"


class TestAllPanelTransformers(TransformerPairwisePanelFixtureGenerator, QuickTester):
    """Module level tests for all sktime pairwise panel transformers."""

    def test_pairwise_transformers_panel(self, estimator_instance, scenario):
        """Main test function for pairwise transformers on tabular data."""
        trafo_name = type(estimator_instance).__name__
        dist_mat = scenario.run(estimator_instance, method_sequence=["transform"])

        X = scenario.args["transform"]["X"]
        len_X = len(scenario.args["transform"]["X"])
        X2 = scenario.args["transform"].get("X2", X)
        len_X2 = len(X2)

        assert isinstance(
            dist_mat, np.ndarray
        ), f"Type of matrix returned by transform is wrong for {trafo_name}"
        assert (
            # this is only true as long as fixture are of mtypes where len = n_instances
            # should that change, use check_is_mtype to get n_instances metadata
            dist_mat.shape
            == (len_X, len_X2)
        ), f"Shape of matrix returned by transform is wrong for {trafo_name}"

    def test_transform_diag(self, estimator_instance, scenario):
        """Test expected output of transform_diag."""
        trafo_name = type(estimator_instance).__name__
        diag_vec = scenario.run(estimator_instance, method_sequence=["transform_diag"])

        len_X = len(scenario.args["transform"]["X"])

        assert isinstance(
            diag_vec, np.ndarray
        ), f"Type of matrix returned by transform is wrong for {trafo_name}"
        assert (
            # this is only true as long as fixture are of mtypes where len = n_instances
            # should that change, use check_is_mtype to get n_instances metadata
            diag_vec.shape
            == (len_X,)
        ), f"Shape of matrix returned by transform is wrong for {trafo_name}"
