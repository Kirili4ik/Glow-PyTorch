import numpy as np
import torch
from scipy import linalg
from torch.nn.functional import adaptive_avg_pool2d
from tqdm import tqdm

from my_utils import calc_z_shapes


def calculate_frechet_distance(mu1, sigma1, mu2, sigma2, eps=1e-6):
    """Numpy implementation of the Frechet Distance.
    The Frechet distance between two multivariate Gaussians X_1 ~ N(mu_1, C_1)
    and X_2 ~ N(mu_2, C_2) is
            d^2 = ||mu_1 - mu_2||^2 + Tr(C_1 + C_2 - 2*sqrt(C_1*C_2)).

    Stable version by Dougal J. Sutherland.

    Params:
    -- mu1   : Numpy array containing the activations of a layer of the
               inception net (like returned by the function 'get_predictions')
               for generated samples.
    -- mu2   : The sample mean over activations, precalculated on an
               representative data set.
    -- sigma1: The covariance matrix over activations for generated samples.
    -- sigma2: The covariance matrix over activations, precalculated on an
               representative data set.

    Returns:
    --   : The Frechet Distance.
    """

    mu1 = np.atleast_1d(mu1)
    mu2 = np.atleast_1d(mu2)

    sigma1 = np.atleast_2d(sigma1)
    sigma2 = np.atleast_2d(sigma2)

    assert mu1.shape == mu2.shape, \
        'Training and test mean vectors have different lengths'
    assert sigma1.shape == sigma2.shape, \
        'Training and test covariances have different dimensions'

    diff = mu1 - mu2

    # Product might be almost singular
    covmean, _ = linalg.sqrtm(sigma1.dot(sigma2), disp=False)
    if not np.isfinite(covmean).all():
        msg = ('fid calculation produces singular product; '
               'adding %s to diagonal of cov estimates') % eps
        print(msg)
        offset = np.eye(sigma1.shape[0]) * eps
        covmean = linalg.sqrtm((sigma1 + offset).dot(sigma2 + offset))

    # Numerical error might give slight imaginary component
    if np.iscomplexobj(covmean):
        if not np.allclose(np.diagonal(covmean).imag, 0, atol=1e-3):
            m = np.max(np.abs(covmean.imag))
            raise ValueError('Imaginary component {}'.format(m))
        covmean = covmean.real

    tr_covmean = np.trace(covmean)

    return (diff.dot(diff) + np.trace(sigma1) +
            np.trace(sigma2) - 2 * tr_covmean)


@torch.no_grad()
def calculate_activation_statistics(config, dataloader, model, inception):
    bs = config.batch
    device = "cuda"
    inception.eval()
    model.eval()
    

    true_vecs, ae_vecs = [], []

    for image, _ in dataloader:
        image = image.to(device)
        # print('img size', image.size())
        # print(inception(image)[0].size())
        true_vecs.append(inception(image)[0].reshape(bs, -1))
        # print(model.generate(image).size())
        # print(inception(model.generate(image))[0].size())
        z_sample = []
        z_shapes = calc_z_shapes(3, config.img_size, config.n_flow, config.n_block)
        for z in z_shapes:
            z_new = torch.randn(bs, *z) * config.temp
            z_sample.append(z_new.to(device))

        # print(len(z_sample), z_sample[-1].size())
        # print(z_sample)
        # print(model.reverse(z_sample).size())
        # print(model.reverse(z_sample))
        pics = model.reverse(z_sample)
        nan_values = torch.sum(
                          torch.isnan(
                              pics.view(-1)
                          )
        ).item()
        if nan_values > 0:
            print(pics.size(), nan_values)
        ae_vecs.append(inception(pics)[0].reshape(bs, -1))

    true_data = torch.stack(true_vecs).detach().cpu().view(bs * len(dataloader), -1).numpy()
    ae_data   = torch.stack(ae_vecs).detach().cpu().view(bs * len(dataloader), -1).numpy()
    
    mu1 = true_data.mean(axis=1)
    mu2 = ae_data.mean(axis=1)

    s1 = np.cov(true_data, rowvar=False)
    s2 = np.cov(ae_data, rowvar=False)

    return mu1, s1, mu2, s2


@torch.no_grad()
def calculate_fid(config, dataloader, model, classifier):
    
    m1, s1, m2, s2 = calculate_activation_statistics(config, dataloader, model, classifier)
    fid_value = calculate_frechet_distance(m1, s1, m2, s2)

    return fid_value.item()
