import numpy as np
from joblib import Parallel, delayed

from . import utils
from .solvers import gl_wrapper


def compute_group_inverse(gains, M, group_info, method="grouplasso",
                          depth=0.9, alpha=0.1, return_stc=True, n_jobs=1,
                          **kwargs):
    """Solves the joint inverse problem for source localization.

    Parameters
    ----------
    gains: array (n_subjects, n_channels, n_sources). forward data, returned by
        `group_model.compute_gains` or `group_model.compute_inv_data`.
    M: array (n_subjects, n_channels, n_times). M-EEG data.
    group_info: dict.
    method: str. Inverse problem model to use. For now, only "grouplasso" is
        supported. The group-lasso solver promotes source estimates with
        overlapping active vertices across subjects. Each time point is
        treated independently.
    depth: float (0-1). Depth weighting. If 1, no normalization is done.
    alpha: float in (0, 1). regularization hyperparameter set as a fraction of
        alpha_max for which all sources are 0.
    return_stc: bool, (optional, default True). If true, source estimates are
        returned as stc objects, array otherwise.
    n_jobs: int (default 1).
    kwargs: additional arguments passed to the solver.

    Return
    ------
    estimates: stc object, array if `return_stc` is False.
    """
    n_subjects, n_channels, n_times = M.shape
    norms = np.linalg.norm(gains, axis=1) ** depth
    gains_scaled = gains / norms[:, None, :]
    gty = np.array([g.T.dot(m) for g, m in zip(gains_scaled, M)])
    alphamax_s = np.linalg.norm(gty, axis=0).max(axis=0)
    alpha_s = alpha * alphamax_s
    it = (delayed(gl_wrapper)(gains_scaled, M[:, :, i], alpha=alpha_s[i],
                              **kwargs) for i in range(n_times))
    coefs, residuals, loss, dg = list(zip(*Parallel(n_jobs=n_jobs)(it)))
    # re-normalize coefs and change units to nAm
    coefs = np.array(coefs) * 1e9 / norms.T[None, :, :]
    log = dict(residuals=residuals, loss=loss, dg=dg)
    stcs = []
    if return_stc:
        hemi = group_info["hemi"]
        vertices_lh = group_info["vertno_lh"]
        vertices_rh = group_info["vertno_rh"]
        subjects = group_info["subjects"]
        for i, (v_l, v_r, subject) in enumerate(zip(vertices_lh, vertices_rh,
                                                    subjects)):
            if hemi == "lh":
                v = [v_l, []]
            elif hemi == "rh":
                v = [[], v_r]
            else:
                v = [v_l, v_r]
            stc = utils.make_stc(coefs[:, :, i].T, v, tmin=group_info["tmin"],
                                 tstep=group_info["tstep"], subject=subject)
            stcs.append(stc)
        return stcs, log
    return coefs, log
