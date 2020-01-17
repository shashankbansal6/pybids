from os.path import join, dirname, abspath

import pytest

from bids.layout import BIDSLayout
from bids.tests import get_test_data_path
from bids.variables import (DenseRunVariable, SparseRunVariable,
                            merge_collections)
from bids.variables.entities import RunInfo

@pytest.fixture(scope="module")
def run_coll():
    path = join(get_test_data_path(), 'ds005')
    layout = BIDSLayout(path)
    return layout.get_collections('run', types=['events'], merge=True,
                                  scan_length=480)


@pytest.fixture(scope="module")
def run_coll_list():
    path = join(get_test_data_path(), 'ds005')
    layout = BIDSLayout(path)
    return layout.get_collections('run', types=['events'], merge=False,
                                  scan_length=480)


def test_run_variable_collection_init(run_coll):
    assert isinstance(run_coll.variables, dict)
    assert run_coll.sampling_rate == 10


def test_run_variable_collection_sparse_variable_accessors(run_coll):
    coll = run_coll.clone()
    assert coll.get_sparse_variables()
    assert coll.all_sparse()
    coll.variables['RT'] = coll.variables['RT'].to_dense(1)
    assert not coll.all_sparse()
    assert len(coll.get_sparse_variables()) + 1 == len(coll.variables)


def test_run_variable_collection_dense_variable_accessors(run_coll):
    coll = run_coll.clone()
    coll.variables['RT'] = coll.variables['RT'].to_dense(1)
    assert not coll.all_dense()
    assert len(coll.get_dense_variables()) == 1
    for k, v in coll.variables.items():
        if k == 'RT':
            continue
        coll.variables[k] = v.to_dense(1)
    assert coll.all_dense()


def test_run_variable_collection_get_sampling_rate(run_coll):
    coll = run_coll.clone()
    assert coll._get_sampling_rate(None) == 10
    assert coll._get_sampling_rate('TR') == 0.5
    coll.variables['RT'].run_info[0] = RunInfo({}, 200, 10, None)
    with pytest.raises(ValueError) as exc:
        coll._get_sampling_rate('TR')
        assert exc.value.message.startswith('Non-unique')
    assert coll._get_sampling_rate('highest') is None
    coll.variables['RT1'] = coll.variables['RT'].to_dense(5.)
    coll.variables['RT2'] = coll.variables['RT'].to_dense(12.)
    assert coll._get_sampling_rate('highest') == 12.
    assert coll._get_sampling_rate(20) == 20
    with pytest.raises(ValueError) as exc:
        coll._get_sampling_rate('BLARGH')
        assert exc.value.message.startswith('Invalid')


def test_resample_run_variable_collection(run_coll):
    run_coll = run_coll.clone()
    resampled = run_coll.resample()
    assert not resampled.variables  # Empty because all variables are sparse

    resampled = run_coll.resample(force_dense=True).variables
    assert len(resampled) == 7
    assert all([isinstance(v, DenseRunVariable) for v in resampled.values()])
    assert len(set([v.sampling_rate for v in resampled.values()])) == 1
    targ_len = 480 * 16 * 3 * 10
    assert all([len(v.values) == targ_len for v in resampled.values()])

    sr = 20
    resampled = run_coll.resample(sr, force_dense=True).variables
    targ_len = 480 * 16 * 3 * sr
    assert all([len(v.values) == targ_len for v in resampled.values()])

    run_coll.resample(sr, force_dense=True, in_place=True)
    assert len(run_coll.variables) == 8
    vars_ = run_coll.variables.values()
    vars_ = [v for v in vars_ if v.name != 'trial_type']
    assert all([len(v.values) == targ_len for v in vars_])
    assert all([v.sampling_rate == sr for v in vars_])
    assert all([isinstance(v, DenseRunVariable) for v in vars_])


def test_run_variable_collection_to_df(run_coll):
    run_coll = run_coll.clone()

    # All variables sparse, wide format
    df = run_coll.to_df()
    assert df.shape == (4096, 15)
    wide_cols = {'onset', 'duration', 'subject', 'run', 'task',
                 'PTval', 'RT', 'gain', 'loss', 'parametric gain', 'respcat',
                 'respnum', 'trial_type', 'suffix', 'datatype'}
    assert set(df.columns) == wide_cols

    # All variables sparse, wide format
    df = run_coll.to_df(format='long')
    assert df.shape == (32768, 9)
    long_cols = {'amplitude', 'duration', 'onset', 'condition', 'run',
                 'task', 'subject', 'suffix', 'datatype'}
    assert set(df.columns) == long_cols

    # All variables dense, wide format
    df = run_coll.to_df(sparse=False)
    assert df.shape == (230400, 18)
    extra_cols = {'TaskName', 'RepetitionTime', 'extension', 'SliceTiming'}
    assert set(df.columns) == (wide_cols | extra_cols) - {'trial_type'}

    # All variables dense, wide format
    df = run_coll.to_df(sparse=False, format='long')
    assert df.shape == (1612800, 13)
    assert set(df.columns) == (long_cols | extra_cols)


def test_merge_collections(run_coll, run_coll_list):
    df1 = run_coll.to_df().sort_values(['subject', 'run', 'onset'])
    rcl = [c.clone() for c in run_coll_list]
    coll = merge_collections(rcl)
    df2 = coll.to_df().sort_values(['subject', 'run', 'onset'])
    assert df1.equals(df2)


def test_get_collection_entities(run_coll_list):
    coll = run_coll_list[0]
    ents = coll.entities
    assert {'run', 'task', 'subject', 'suffix', 'datatype'} == set(ents.keys())

    merged = merge_collections(run_coll_list[:3])
    ents = merged.entities
    assert {'task', 'subject', 'suffix', 'datatype'} == set(ents.keys())
    assert ents['subject'] == '01'

    merged = merge_collections(run_coll_list[3:6])
    ents = merged.entities
    assert {'task', 'subject', 'suffix', 'datatype'} == set(ents.keys())
    assert ents['subject'] == '02'


def test_match_variables(run_coll):
    matches = run_coll.match_variables('^.{1,2}a', match_type='regex')
    assert set(matches) == {'gain', 'parametric gain'}
    assert not run_coll.match_variables('.{1,3}a')
    matches = run_coll.match_variables('^.{1,2}a', match_type='regex',
                                       return_type='variable')
    assert len(matches) == 2
    assert all([isinstance(m, SparseRunVariable) for m in matches])
    matches = run_coll.match_variables('*gain')
    assert set(matches) == {'gain', 'parametric gain'}
