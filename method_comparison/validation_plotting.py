# general imports
import warnings
import numpy as np
import tensorflow as tf
from tensorflow.keras.layers import Input, Dense, Lambda, Flatten, Softmax, ReLU, ELU, LeakyReLU
from tensorflow.keras.layers import concatenate as concat
from tensorflow.keras.models import Model, Sequential
from tensorflow.keras import backend as K
from tensorflow.keras.losses import mean_absolute_error, mean_squared_error, KLDivergence
from tensorflow.keras.datasets import mnist
from tensorflow.keras.activations import relu, linear
from tensorflow.keras.utils import to_categorical, normalize, plot_model
from tensorflow.keras.callbacks import EarlyStopping
from tensorflow.keras.optimizers import Adam, SGD
import matplotlib.pyplot as plt
from scipy.spatial import distance_matrix
from scipy.stats import spearmanr, pearsonr, ttest_ind, wilcoxon
from scipy.spatial.distance import euclidean
from sklearn.model_selection import StratifiedShuffleSplit
from sklearn.metrics import accuracy_score
from PIL import Image

from tqdm import tnrange, tqdm_notebook
import ipywidgets

# Images, plots, display, and visualization
import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns
from sklearn.manifold import TSNE
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import scale, MinMaxScaler
from matplotlib_venn import venn2
from upsetplot import from_contents, UpSet

# programming stuff
import time
import os
import pickle
from pathlib import Path

# for each sample calculate the transformation / projection in PCA space

def get_samp_transform_vec_VAE(X_full, meta_df, start_samp, end_samp, encoder, decoder, batch_size):
    # get the perturbation latent code
    idx_start_train = np.logical_and(meta_df.stim == "CTRL", meta_df.isTraining == "Train")
    idx_start_train = np.logical_and(idx_start_train, meta_df.sample_id == start_samp)
    idx_start_train = np.where(idx_start_train)[0]


    idx_end_train = np.logical_and(meta_df.stim == "CTRL", meta_df.isTraining == "Train")
    idx_end_train = np.logical_and(idx_end_train, meta_df.sample_id == end_samp)
    idx_end_train = np.where(idx_end_train)[0]
    idx_end_train = np.tile(idx_end_train, 50)

    X_start = X_full[idx_start_train]
    mu_slack, z_slack = encoder.predict(X_start, batch_size=batch_size)
    train_start = decoder.predict(mu_slack, batch_size=batch_size)

    X_end = X_full[idx_end_train]
    mu_slack, z_slack = encoder.predict(X_end, batch_size=batch_size)
    train_end = decoder.predict(mu_slack, batch_size=batch_size)


    train_start_med = np.median(train_start, axis=0)
    train_end_med = np.median(train_end, axis=0)

    proj_train = train_start_med - train_end_med
    return proj_train


def get_pert_transform_vec_VAE(X_full, meta_df, curr_samp, encoder, decoder, batch_size):

    # get the perturbation latent code
    idx_stim_train = np.logical_and(meta_df.samp_type == "bulk", meta_df.isTraining == "Train")
    idx_stim_train = np.logical_and(idx_stim_train, meta_df.stim == "STIM")
    idx_stim_train = np.logical_and(idx_stim_train, meta_df.sample_id == curr_samp)
    idx_stim_train = np.where(idx_stim_train)[0]
    idx_stim_train = np.tile(idx_stim_train, 50)

    idx_ctrl_train = np.logical_and(meta_df.samp_type == "bulk", meta_df.isTraining == "Train")
    idx_ctrl_train = np.logical_and(idx_ctrl_train, meta_df.stim == "CTRL")
    idx_ctrl_train = np.logical_and(idx_ctrl_train, meta_df.sample_id == curr_samp)
    idx_ctrl_train = np.where(idx_ctrl_train)[0]
    idx_ctrl_train = np.tile(idx_ctrl_train, 50)

    X_ctrl = X_full[idx_ctrl_train]
    mu_slack, z_slack = encoder.predict(X_ctrl, batch_size=batch_size)
    train_ctrl = decoder.predict(mu_slack, batch_size=batch_size)

    X_stim = X_full[idx_stim_train]
    mu_slack, z_slack = encoder.predict(X_stim, batch_size=batch_size)
    train_stim = decoder.predict(mu_slack, batch_size=batch_size)


    train_stim_med = np.median(train_stim, axis=0)
    train_ctrl_med = np.median(train_ctrl, axis=0)

    proj_train = train_stim_med - train_ctrl_med

    return proj_train

def calc_VAE_perturbation(X_full, meta_df, encoder, decoder, 
                           scaler, batch_size):
    # get the perturbation latent code
    idx_sc_ref = np.logical_and(meta_df.stim == "CTRL", meta_df.isTraining == "Train")
    idx_sc_ref = np.logical_and(idx_sc_ref, meta_df.samp_type == "sc_ref")
    idx_sc_ref = np.logical_and(idx_sc_ref, meta_df.cell_prop_type == "cell_type_specific")
    idx_sc_ref = np.logical_and(idx_sc_ref, meta_df.sample_id == "1015")
    idx_sc_ref = np.where(idx_sc_ref)[0]
    sc_ref_meta_df = meta_df.iloc[idx_sc_ref]

    X_sc_ref = np.copy(X_full)
    X_sc_ref = X_sc_ref[idx_sc_ref,]

    ## get the transformation vectors
    proj_samp_dict = {}
    proj_pert_dict = {}
    start_samps = ['1015'] #['1015', '1256']
    end_samps = ['1488', '1244', '1016', '101', '1039', '107']
    for start_samp in start_samps:
        for end_samp in end_samps:
            proj_vec = get_samp_transform_vec_VAE(X_full, meta_df, start_samp, end_samp, encoder, decoder, batch_size)
            proj_samp_dict[f"{start_samp}_{end_samp}"] = proj_vec
    for curr_samp in end_samps:
        proj_vec = get_pert_transform_vec_VAE(X_full, meta_df, curr_samp, encoder, decoder, batch_size)
        proj_pert_dict[curr_samp] = proj_vec


    # get the CTRL
    mu_slack, z_slack = encoder.predict(X_sc_ref, batch_size=batch_size)
    single_decoded_0_0 = decoder.predict(z_slack, batch_size=batch_size)
    single_decoded_0_1 = np.copy(single_decoded_0_0)

    # do the projections
    decoded_0_0 = None
    decoded_0_1 = None
    final_meta_df = None
    for curr_samp_end in end_samps:
        curr_decoded_0_0 = single_decoded_0_0.copy()
        curr_decoded_0_1 = single_decoded_0_1.copy()
        curr_meta_df = sc_ref_meta_df.copy()
        for curr_idx in range(X_sc_ref.shape[0]):
            # project for each initial sample
            curr_samp_start = curr_meta_df.iloc[curr_idx].sample_id
            # project to sample
            proj_samp_vec = proj_samp_dict[f"{curr_samp_start}_{curr_samp_end}"]
            # project to perturbation
            proj_pert_vec = proj_pert_dict[curr_samp_end]

            curr_decoded_0_0[curr_idx] = curr_decoded_0_0[curr_idx] + proj_samp_vec
            curr_decoded_0_1[curr_idx] = curr_decoded_0_0[curr_idx] + proj_pert_vec
            curr_meta_df.iloc[curr_idx].sample_id = curr_samp_end
            curr_meta_df.iloc[curr_idx].isTraining = "Test"

        ### append new df
        if final_meta_df is None:
            decoded_0_0 = curr_decoded_0_0
            decoded_0_1 = curr_decoded_0_1
            final_meta_df = curr_meta_df
        else:
            decoded_0_0 = np.append(decoded_0_0, curr_decoded_0_0, axis=0)
            decoded_0_1 = np.append(decoded_0_1, curr_decoded_0_1, axis=0)
            final_meta_df = final_meta_df.append(curr_meta_df)

    decoded_0_1 = scaler.inverse_transform(decoded_0_1)

    decoded_0_0 = scaler.inverse_transform(decoded_0_0)


    return (final_meta_df, decoded_0_0, decoded_0_1)


def get_samp_transform_vec_PCA(X_full, meta_df, start_samp, end_samp, fit):
    # get the perturbation latent code
    idx_start_train = np.logical_and(meta_df.stim == "CTRL", meta_df.isTraining == "Train")
    idx_start_train = np.logical_and(idx_start_train, meta_df.sample_id == start_samp)
    idx_start_train = np.where(idx_start_train)[0]


    idx_end_train = np.logical_and(meta_df.stim == "CTRL", meta_df.isTraining == "Train")
    idx_end_train = np.logical_and(idx_end_train, meta_df.sample_id == end_samp)
    idx_end_train = np.where(idx_end_train)[0]

    X_start = X_full[idx_start_train]
    train_start = fit.transform(X_start)

    X_end = X_full[idx_end_train]
    train_end = fit.transform(X_end)


    train_start_med = np.median(train_start, axis=0)
    train_end_med = np.median(train_end, axis=0)

    proj_train = train_start_med - train_end_med
    return(proj_train)


def get_pert_transform_vec_PCA(X_full, meta_df, curr_samp, fit):
    # get the perturbation latent code
    idx_stim_train = np.logical_and(meta_df.samp_type == "bulk", meta_df.isTraining == "Train")
    idx_stim_train = np.logical_and(idx_stim_train, meta_df.stim == "STIM")
    idx_stim_train = np.logical_and(idx_stim_train, meta_df.sample_id == curr_samp)
    idx_stim_train = np.where(idx_stim_train)[0]


    idx_ctrl_train = np.logical_and(meta_df.samp_type == "bulk", meta_df.isTraining == "Train")
    idx_ctrl_train = np.logical_and(idx_ctrl_train, meta_df.stim == "CTRL")
    idx_ctrl_train = np.logical_and(idx_ctrl_train, meta_df.sample_id == curr_samp)
    idx_ctrl_train = np.where(idx_ctrl_train)[0]

    X_ctrl = X_full[idx_ctrl_train]
    train_ctrl = fit.transform(X_ctrl)

    X_stim = X_full[idx_stim_train]
    train_stim = fit.transform(X_stim)


    train_stim_med = np.median(train_stim, axis=0)
    train_ctrl_med = np.median(train_ctrl, axis=0)

    proj_train = train_stim_med - train_ctrl_med
    return(proj_train)

def calc_PCA_perturbation(X_full, meta_df, scaler, fit):

    # get the perturbation latent code
    idx_sc_ref = np.logical_and(meta_df.stim == "CTRL", meta_df.isTraining == "Train")
    idx_sc_ref = np.logical_and(idx_sc_ref, meta_df.samp_type == "sc_ref")
    idx_sc_ref = np.logical_and(idx_sc_ref, meta_df.cell_prop_type == "cell_type_specific")
    idx_sc_ref = np.logical_and(idx_sc_ref, meta_df.sample_id == "1015")
    idx_sc_ref = np.where(idx_sc_ref)[0]
    sc_ref_meta_df = meta_df.iloc[idx_sc_ref]

    X_sc_ref = np.copy(X_full)
    X_sc_ref = X_sc_ref[idx_sc_ref,]

    ## get the transofrmation vectors
    proj_samp_dict = {}
    proj_pert_dict = {}
    start_samps = ['1015'] #['1015', '1256']
    end_samps = ['1488', '1244', '1016', '101', '1039', '107']
    for start_samp in start_samps:
        for end_samp in end_samps:
            proj_vec = get_samp_transform_vec_PCA(X_full, meta_df, start_samp, end_samp, fit)
            proj_samp_dict[f"{start_samp}_{end_samp}"] = proj_vec
    for curr_samp in end_samps:
        proj_vec = get_pert_transform_vec_PCA(X_full, meta_df, curr_samp, fit)
        proj_pert_dict[curr_samp] = proj_vec


    # now get the refernce sample that we will use to do all projectsions
    single_decoded_0_0 = fit.transform(X_sc_ref)
    single_decoded_0_1 = np.copy(single_decoded_0_0)

    # do the projections
    decoded_0_0 = None
    decoded_0_1 = None
    final_meta_df = None
    for curr_samp_end in end_samps:
        curr_decoded_0_0 = single_decoded_0_0.copy()
        curr_decoded_0_1 = single_decoded_0_1.copy()
        curr_meta_df = sc_ref_meta_df.copy()
        for curr_idx in range(X_sc_ref.shape[0]):
            # project for each initial sample
            curr_samp_start = curr_meta_df.iloc[curr_idx].sample_id
            # project to sample
            proj_samp_vec = proj_samp_dict[f"{curr_samp_start}_{curr_samp_end}"]
            # project to perturbation
            proj_pert_vec = proj_pert_dict[curr_samp_end]

            curr_decoded_0_0[curr_idx] = curr_decoded_0_0[curr_idx] + proj_samp_vec
            curr_decoded_0_1[curr_idx] = curr_decoded_0_0[curr_idx] + proj_pert_vec
            curr_meta_df.iloc[curr_idx].sample_id = curr_samp_end
            curr_meta_df.iloc[curr_idx].isTraining = "Test"

        ### append new df
        if final_meta_df is None:
            decoded_0_0 = curr_decoded_0_0
            decoded_0_1 = curr_decoded_0_1
            final_meta_df = curr_meta_df
        else:
            decoded_0_0 = np.append(decoded_0_0, curr_decoded_0_0, axis=0)
            decoded_0_1 = np.append(decoded_0_1, curr_decoded_0_1, axis=0)
            final_meta_df = final_meta_df.append(curr_meta_df)


    decoded_0_1 = fit.inverse_transform(decoded_0_1)
    decoded_0_1 = scaler.inverse_transform(decoded_0_1)

    decoded_0_0 = fit.inverse_transform(decoded_0_0)
    decoded_0_0 = scaler.inverse_transform(decoded_0_0)

    return (final_meta_df, decoded_0_0, decoded_0_1)

def calc_CVAE_perturbation(X_full, meta_df, encoder, decoder, 
                           scaler, batch_size, 
                           label_1hot_full, drug_1hot_full):

    label_1hot_temp = np.copy(label_1hot_full)
    perturb_1hot_temp = np.copy(drug_1hot_full)


    # get the single cell data 
    idx_sc_ref = np.logical_and(meta_df.stim == "CTRL", meta_df.isTraining == "Train")
    idx_sc_ref = np.logical_and(idx_sc_ref, meta_df.samp_type == "sc_ref")
    idx_sc_ref = np.logical_and(idx_sc_ref, meta_df.cell_prop_type == "cell_type_specific")
    idx_sc_ref = np.where(idx_sc_ref)[0]

    ## this is to match up sample amounts across comparators
    idx_sc_ref = np.tile(idx_sc_ref, 6) 


    X_sc_ref = np.copy(X_full)
    X_sc_ref = X_sc_ref[idx_sc_ref,]

    # get the sample_ids we will perturb
    sample_interest = ['1488', '1244', '1016', '101', '1039', '107']
    sample_code_idx = np.logical_and(meta_df.cell_prop_type == "cell_type_specific", 
                                        np.isin(meta_df.sample_id, sample_interest))
    sample_code_idx = np.where(sample_code_idx)[0]
    sample_code = label_1hot_temp[sample_code_idx]

    # make the metadata file
    ctrl_test_meta_df = meta_df.copy()
    ctrl_test_meta_df = ctrl_test_meta_df.iloc[sample_code_idx]
    ctrl_test_meta_df.isTraining = "Test"
    ctrl_test_meta_df.stim = "CTRL"

    # get the perturb code
    idx_stim = np.where(meta_df.stim == "STIM")[0][range(6000)]
    idx_stim = np.tile(idx_stim, 2)
    perturbed_code = perturb_1hot_temp[idx_stim]

    idx_ctrl = np.where(meta_df.stim == "CTRL")[0][range(6000)]
    idx_ctrl = np.tile(idx_ctrl, 2)
    unperturbed_code = perturb_1hot_temp[idx_ctrl]


    mu_slack = encoder.predict([X_sc_ref, sample_code, perturbed_code], batch_size=batch_size)
    z_concat = np.hstack([mu_slack, sample_code, perturbed_code])
    decoded_0_1 = decoder.predict(z_concat, batch_size=batch_size)
    decoded_0_1 = scaler.inverse_transform(decoded_0_1)


    mu_slack = encoder.predict([X_sc_ref, sample_code, unperturbed_code], batch_size=batch_size)
    z_concat = np.hstack([mu_slack, sample_code, unperturbed_code])
    decoded_0_0 = decoder.predict(z_concat, batch_size=batch_size)
    decoded_0_0 = scaler.inverse_transform(decoded_0_0)

    return (ctrl_test_meta_df, decoded_0_0, decoded_0_1)


def calc_buddi_perturbation(meta_df, X_full, scaler, classifier, encoder_unlab, decoder, batch_size):

    # get the perturbation latent code
    idx_stim_test = np.logical_and(meta_df.stim == "STIM", meta_df.isTraining == "Test")
    idx_stim_test = np.where(idx_stim_test)[0]
    stim_test_meta_df = meta_df.iloc[idx_stim_test]

    # duplicate to we have correct batch size
    len_stim_test = len(idx_stim_test)
    idx_stim_test = np.tile(idx_stim_test, 5)

    X_pert = np.copy(X_full)
    X_pert = X_pert[idx_stim_test,]

    prop_outputs = classifier.predict(X_pert, batch_size=batch_size)
    Y_pert = np.copy(prop_outputs)
    Y_pert = np.argmax(Y_pert, axis=1)

    z_slack, mu_slack, l_sigma_slack, z_rot, mu_rot, l_sigma_rot, z_drug_perturb, mu_drug, l_sigma_drug = encoder_unlab.predict(X_pert, batch_size=batch_size)

    # get the original perturbation output
    z_concat_perturb = np.hstack([z_slack, prop_outputs, z_rot, z_drug_perturb])
    decoded_1_1 = decoder.predict(z_concat_perturb, batch_size=batch_size)
    decoded_1_1 = scaler.inverse_transform(decoded_1_1)
    decoded_1_1 = decoded_1_1[range(len_stim_test),]

    # now get ctrl test cells
    idx_ctrl_test = np.logical_and(meta_df.stim == "CTRL", meta_df.isTraining == "Test")
    idx_ctrl_test = np.where(idx_ctrl_test)[0]
    ctrl_test_meta_df = meta_df.iloc[idx_ctrl_test]


    # duplicate to we have correct batch size
    len_ctrl_test = len(idx_ctrl_test)
    idx_ctrl_test = np.tile(idx_ctrl_test, 5)


    X_temp = np.copy(X_full)
    X_temp = X_temp[idx_ctrl_test,]

    prop_outputs = classifier.predict(X_temp, batch_size=batch_size)
    Y_temp = np.copy(prop_outputs)
    Y_temp = np.argmax(Y_temp, axis=1)

    # get the perturbation latent code

    # now get each of the latent codes
    z_slack, mu_slack, l_sigma_slack, z_rot, mu_rot, l_sigma_rot, z_drug, mu_drug, l_sigma_drug = encoder_unlab.predict(X_temp, batch_size=batch_size)

    # get the stim latent codes
    z_drug_perturb = z_drug_perturb[np.random.choice(z_drug_perturb.shape[0], X_temp.shape[0], replace=True)]


    # now concatenate together and add the stim codes to the latent
    z_concat_unlab_perturb = np.hstack([z_slack, prop_outputs, z_rot, z_drug_perturb])
    decoded_0_1 = decoder.predict(z_concat_unlab_perturb, batch_size=batch_size)
    decoded_0_1 = scaler.inverse_transform(decoded_0_1)
    decoded_0_1 = decoded_0_1[range(len_stim_test),]

    # now concatenate together and add the stim codes to the latent
    z_concat_unlab_perturb = np.hstack([z_slack, prop_outputs, z_rot, z_drug])
    decoded_0_0 = decoder.predict(z_concat_unlab_perturb, batch_size=batch_size)
    decoded_0_0 = scaler.inverse_transform(decoded_0_0)
    decoded_0_0 = decoded_0_0[range(len_ctrl_test),]

    return (stim_test_meta_df, ctrl_test_meta_df, decoded_1_1, decoded_0_1, decoded_0_0)

def subset_sample_celltype_perturbation(X_full, decoded_0_0, decoded_0_1, scaler, samp_interest, cell_prop_type, meta_df, ctrl_test_meta_df, cell_type_interest=None):

    # get the real data
    X_tmp = np.copy(X_full)
    X_tmp = scaler.inverse_transform(X_tmp)

    # get the ground truth
    real_stimulated_idx = np.logical_and(meta_df.stim == "STIM", meta_df.isTraining == "Test")
    real_stimulated_idx = np.logical_and(real_stimulated_idx, meta_df.cell_prop_type == cell_prop_type)
    real_stimulated_idx = np.logical_and(real_stimulated_idx, meta_df.sample_id == samp_interest)

    if cell_type_interest is not None:
        real_stimulated_idx = np.logical_and(real_stimulated_idx, meta_df.Y_max == cell_type_interest)
    real_stimulated_idx = np.where(real_stimulated_idx)[0]
    real_original_stim = X_tmp[real_stimulated_idx]


    real_ctrl_idx = np.logical_and(meta_df.stim == "CTRL", meta_df.isTraining == "Test")
    real_ctrl_idx = np.logical_and(real_ctrl_idx, meta_df.cell_prop_type == cell_prop_type)
    real_ctrl_idx = np.logical_and(real_ctrl_idx, meta_df.sample_id == samp_interest)
    if cell_type_interest is not None:
        real_ctrl_idx = np.logical_and(real_ctrl_idx, meta_df.Y_max == cell_type_interest)
    real_ctrl_idx = np.where(real_ctrl_idx)[0]
    real_original_ctrl = X_tmp[real_ctrl_idx]


    # get the reconstructed 
    recon_Zstim_idx = np.logical_and(ctrl_test_meta_df.stim == "CTRL", ctrl_test_meta_df.isTraining == "Test")
    recon_Zstim_idx = np.logical_and(recon_Zstim_idx, ctrl_test_meta_df.cell_prop_type == cell_prop_type)
    #recon_Zstim_idx = np.logical_and(recon_Zstim_idx, ctrl_test_meta_df.sample_id == samp_interest)
    if cell_type_interest is not None:
        recon_Zstim_idx = np.logical_and(recon_Zstim_idx, ctrl_test_meta_df.Y_max == cell_type_interest)
    recon_Zstim_idx = np.where(recon_Zstim_idx)[0]
    projected_Zstimulated = decoded_0_1[recon_Zstim_idx]
    projected_ctrl = decoded_0_0[recon_Zstim_idx]

    return (real_original_stim, real_original_ctrl, projected_Zstimulated, projected_ctrl)



def calc_expr_log2FC_r2(real_ctrl, real_stim, proj_ctrl, proj_stim):

    real_stim_med = np.median(real_stim, axis=0)
    proj_stim_med = np.median(proj_stim, axis=0)
    expr_r2_stim = spearmanr(real_stim_med, proj_stim_med)[0]

    real_ctrl_med = np.median(real_ctrl, axis=0)
    proj_ctrl_med = np.median(proj_ctrl, axis=0)
    expr_r2_ctrl = spearmanr(real_ctrl_med, proj_ctrl_med)[0]


    real_ctrl = np.median(real_ctrl, axis=0)+1
    real_stim = np.median(real_stim, axis=0)+1
    real_log2FC = np.log2(real_stim/real_ctrl)

    proj_ctrl = np.median(proj_ctrl, axis=0)+1
    proj_stim = np.median(proj_stim, axis=0)+1
    proj_log2FC = np.log2(proj_stim/proj_ctrl)


    log2FC_r2 = spearmanr(real_log2FC, proj_log2FC)[0]

    # do the same for bottom 30, mid and top
    real_ctrl_quantiles = np.quantile(real_ctrl, [0.33, 0.66])
    bottom_30 = np.where(real_ctrl < real_ctrl_quantiles[0])
    mid_30 = np.where(np.logical_and(real_ctrl > real_ctrl_quantiles[0], real_ctrl < real_ctrl_quantiles[1]))
    top_30 = np.where(real_ctrl > real_ctrl_quantiles[1])

    log2FC_r2_bottom = spearmanr(real_log2FC[bottom_30], proj_log2FC[bottom_30])[0]
    log2FC_r2_mid = spearmanr(real_log2FC[mid_30], proj_log2FC[mid_30])[0]
    log2FC_r2_top = spearmanr(real_log2FC[top_30], proj_log2FC[top_30])[0]

    log2FC_rmse = np.sqrt(np.mean((proj_log2FC-real_log2FC)**2))

    return (expr_r2_stim, expr_r2_ctrl, log2FC_r2, log2FC_r2_bottom, log2FC_r2_mid, log2FC_r2_top, log2FC_rmse)


def get_TP_FP_DE_genes(projected_Zstimulated, projected_ctrl, DE_table, gene_cutoff=100, pvalue_cutoff=0.01):
    test_res = ttest_ind(projected_Zstimulated, projected_ctrl)
    top_test_res = union_genes[np.argsort(test_res.pvalue)[0:gene_cutoff]]

    DE_table = DE_table.sort_values(by=['padj'])
    DE_table.gene_symbol.to_list()[0:gene_cutoff]

    num_intersect_genes = len(np.intersect1d(top_test_res, DE_table))

    num_DE = len(np.where(test_res.pvalue < pvalue_cutoff)[0])

    return(num_intersect_genes, num_DE)


def get_pca_for_plotting(encodings):

    from sklearn.decomposition import PCA

    fit = PCA(n_components=2)
    pca_results = fit.fit_transform(encodings)

    plot_df = pd.DataFrame(pca_results[:,0:2])
    print(pca_results.shape)
    print(plot_df.shape)
    plot_df.columns = ['PCA_0', 'PCA_1']
    return plot_df

def plot_pca(plot_df, color_vec, ax, title="", alpha=0.1):

    plot_df['Y'] = color_vec

    g = sns.scatterplot(
        x="PCA_0", y="PCA_1",
        data=plot_df,
        hue="Y",
        palette=sns.color_palette("hls", len(np.unique(color_vec))),
        legend="full",
        alpha=alpha, ax= ax
    )

    ax.set_title(title)
    sns.move_legend(ax, "upper left", bbox_to_anchor=(1, 1))

    return g

def get_tsne_for_plotting(encodings):
    tsne = TSNE(n_components=2, verbose=1, perplexity=20, n_iter=500)
    tsne_results = tsne.fit_transform(encodings)

    plot_df = pd.DataFrame(tsne_results[:,0:2])
    print(tsne_results.shape)
    print(plot_df.shape)
    plot_df.columns = ['tsne_0', 'tsne_1']
    return plot_df

def plot_tsne(plot_df, color_vec, ax, title=""):

    plot_df['Y'] = color_vec

    g = sns.scatterplot(
        x="tsne_0", y="tsne_1",
        data=plot_df,
        hue="Y",
        palette=sns.color_palette("hls", len(np.unique(color_vec))),
        legend="full",
        alpha=0.3, ax= ax
    )

    ax.set_title(title)
    sns.move_legend(ax, "upper left", bbox_to_anchor=(1, 1))

    return g

import umap

def get_umap_for_plotting(encodings):
    fit = umap.UMAP()
    umap_results = fit.fit_transform(encodings)

    plot_df = pd.DataFrame(umap_results[:,0:2])
    print(umap_results.shape)
    print(plot_df.shape)
    plot_df.columns = ['umap_0', 'umap_1']
    return plot_df

def plot_umap(plot_df, color_vec, ax, title="", alpha=0.3):

    plot_df['Y'] = color_vec

    g = sns.scatterplot(
        x="umap_0", y="umap_1",
        data=plot_df,
        hue="Y",
        palette=sns.color_palette("hls", len(np.unique(color_vec))),
        legend="full",
        alpha=alpha, ax= ax
    )

    ax.set_title(title)
    sns.move_legend(ax, "upper left", bbox_to_anchor=(1, 1))

    return g

def plot_expr_corr(xval, yval, ax, title, xlab, ylab, class_id, max_val=2700, min_val=0, alpha=0.5):

    plot_df = pd.DataFrame(list(zip(xval, yval)))
    plot_df.columns = [xlab, ylab]

    g = sns.scatterplot(
        x=xlab, y=ylab,
        data=plot_df,ax=ax,
        hue=class_id,
        alpha= alpha
    )
    g.set(ylim=(min_val, max_val))
    g.set(xlim=(min_val, max_val))
    g.plot([min_val, max_val], [min_val, max_val], transform=g.transAxes)


    ax.set_title(title)
    return g

def plot_MA(xval, yval, ax, title, xlab, ylab, class_id, max_val=2700, min_val=0, alpha=0.5):

    plot_df = pd.DataFrame(list(zip(xval, yval)))
    plot_df.columns = [xlab, ylab]

    g = sns.scatterplot(
        x=xlab, y=ylab,
        data=plot_df,ax=ax,
        hue=class_id,
        alpha=alpha
    )
    g.set(ylim=(min_val, max_val))
    g.set(xlim=(min_val, max_val))


    ax.set_title(title)
    return g