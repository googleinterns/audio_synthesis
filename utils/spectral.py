# Copyright 2020 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Provides functionality for converting audio representations."""

import tensorflow as tf
import numpy as np
from librosa.core import griffinlim

_EPSILON = 1e-6
_SAMPLE_RATE = 16000
WINDOW_FN = tf.signal.hamming_window


def _linear_to_mel_scale(linear_scale_in, n_mel_bins, mel_lower_hertz_edge,
                         mel_upper_hertz_edge):
    """Converts a linear scale to a mel scale.

    Args:
        linear_scale_in: The linear scale spectogram. Expected shape is
            [-1, time, frequency, 1].
        n_mel_bins: The number of mel bins.
        mel_lower_hertz_edge: The lowest frequency in hertz to include in the
            mel spectrum
        mel_upper_hertz_edge: The highest frequency in hertz to include in the
            mel spectrum

    Returns:
        The linear_scale_in transformed to the mel domain, according to the
        given paramaters. Shape is linear_scale_in.shape, except shape[-1] =
        n_mel_bins.
    """

    linear_to_mel_weight_matrix = tf.signal.linear_to_mel_weight_matrix(
        n_mel_bins, linear_scale_in.shape[-1], _SAMPLE_RATE, mel_lower_hertz_edge,
        mel_upper_hertz_edge
    )

    mel_scale_out = tf.tensordot(linear_scale_in, linear_to_mel_weight_matrix, 1)
    return mel_scale_out

def _mel_to_linear_scale(mel_scale_in, n_stft_bins, mel_lower_hertz_edge,
                         mel_upper_hertz_edge):
    """Converts a mel scale to a linear scale, using the pseudo inverse
    of the filterbank.

    Args:
        mel_scale_in: The mel scale spectogram. Expected shape is
            [-1, time, frequency, 1] or [-1, time, frequency, 2].
        n_stft_bins: The number of stft bins.
        mel_lower_hertz_edge: The lowest frequency in hertz to include in the
            mel spectrum
        mel_upper_hertz_edge: The highest frequency in hertz to include in the
            mel spectrum

    Returns:
        The mel_scale_in transformed to the linear domain, according to the
        given paramaters. Shape is mel_scale_in.shape, except shape[-1] =
        n_stft_bins.
    """

    linear_to_mel_weight_matrix = tf.signal.linear_to_mel_weight_matrix(
        mel_scale_in.shape[-1], n_stft_bins, _SAMPLE_RATE, mel_lower_hertz_edge,
        mel_upper_hertz_edge
    )
    mel_to_linear_weight_matrix = tf.linalg.pinv(linear_to_mel_weight_matrix)

    linear_scale_out = tf.tensordot(mel_scale_in, mel_to_linear_weight_matrix, 1)
    return linear_scale_out

def waveform_2_stft(waveform, frame_length=512, frame_step=128, n_mel_bins=None,
                    mel_lower_hertz_edge=0.0, mel_upper_hertz_edge=8000.0):
    """Transforms a Waveform into the STFT domain.

    Args:
        waveform: The waveform to be transformed. Expected
            shape is [time] or [batch, time].
        frame_length: The length of each stft frame.
        frame_step: Time increment after each frame, i.e.
            overlap=frame_length - frame_step.
        n_mel_bins: The number of mel bins.
        mel_lower_hertz_edge: The lowest frequency in hertz to include in the
            mel spectrum
        mel_upper_hertz_edge: The highest frequency in hertz to include in the
            mel spectrum

    Returns:
        The STFT representation of the input waveform(s). Shape
        is [-1, time_bins, frequency, 2]
    """

    if len(waveform.shape) == 1:
        waveform = tf.expand_dims(waveform, 0)

    stft = tf.signal.stft(
        waveform, frame_length=frame_length, frame_step=frame_step,
        pad_end=True, window_fn=WINDOW_FN
    )

    # Truncate the nyquist frequency, commonly done in other papers,
    # also makes computation easier.
    real = tf.math.real(stft)[:, :, 0:-1]
    img = tf.math.imag(stft)[:, :, 0:-1]

    if n_mel_bins:
        real = _linear_to_mel_scale(
            real, n_mel_bins, mel_lower_hertz_edge, mel_upper_hertz_edge
        )
        img = _linear_to_mel_scale(
            img, n_mel_bins, mel_lower_hertz_edge, mel_upper_hertz_edge
        )

    return tf.concat([tf.expand_dims(real, 3),
                      tf.expand_dims(img, 3)], axis=-1)

def stft_2_waveform(stft, frame_length=512, frame_step=128, n_mel_bins=None,
                    mel_lower_hertz_edge=0.0, mel_upper_hertz_edge=8000.0):
    """Transforms a STFT domain signal into a Waveform.

    Args:
        stft: The stft signal to be transformed. Expected
            shape is [time, frequency, 2] or [batch, time, frequency, 2].
        frame_length: The length of each stft frame.
        frame_step: Time increment after each frame, i.e.
            overlap=frame_length - frame_step.
        n_mel_bins: The number of mel bins.
        mel_lower_hertz_edge: The lowest frequency in hertz to include in the
            mel spectrum
        mel_upper_hertz_edge: The highest frequency in hertz to include in the
            mel spectrum

    Returns:
        The waveform representation of the input STFT(s). Shape
        is [-1, signal_length]
    """

    if len(stft.shape) == 3:
        stft = tf.expand_dims(stft, 0)

    # Set the nyquist frequency to zero (the band we earlier removed).
    # This is also commonly done in these other papers.
    real = stft[:, :, :, 0]
    img = stft[:, :, :, 1]

    if n_mel_bins:
        real = _mel_to_linear_scale(
            real, frame_length//2, mel_lower_hertz_edge, mel_upper_hertz_edge
        )
        img = _mel_to_linear_scale(
            img, frame_length//2, mel_lower_hertz_edge, mel_upper_hertz_edge
        )

    real = tf.pad(real, [[0, 0], [0, 0], [0, 1]], constant_values=0)
    img = tf.pad(img, [[0, 0], [0, 0], [0, 1]], constant_values=0)

    stft = tf.complex(real, img)
    inv_window_fn = tf.signal.inverse_stft_window_fn(frame_step, forward_window_fn=WINDOW_FN)
    waveform = tf.signal.inverse_stft(
        stft, frame_length=frame_length, frame_step=frame_step, window_fn=inv_window_fn
    )
    return waveform

def waveform_2_spectogram(waveform, frame_length=512, frame_step=128,
                          log_magnitude=True, instantaneous_frequency=True,
                          n_mel_bins=None, mel_lower_hertz_edge=0.0,
                          mel_upper_hertz_edge=8000.0):
    """Transforms a Waveform to a Spectogram.

    Returns the spectrogram for the given input. Note, this function
    clips the last frequency band to make the resulting dimension
    a power of two.

    Args:
        waveform: the signal to be transformed. Expected
            shape is [time] or [batch, time]
        frame_length: The length of each stft frame.
        frame_step: Time increment after each frame, i.e.
            overlap=frame_length - frame_step.
        log_magnitude: If true, the log-magnitude will be returned.
        instantaneous_frequency: If true, the instantaneous frequency will,
            be returned instead of phase.
        n_mel_bins: If specified, a spectogram in the mel scale will be
            returned.
        mel_lower_hertz_edge: The minimum frequency to be included in the
            mel-spectogram
        mel_upper_hertz_edge: The highest frequency to be included in the
            mel-spectogram

    Returns:
        A spectogram representation of the input waveform. Shape
        is [-1, time_bins, frequency, 2]
    """

    if len(waveform.shape) == 1:
        waveform = tf.expand_dims(waveform, 0)

    stft = tf.signal.stft(
        waveform, frame_length=frame_length, frame_step=frame_step,
        pad_end=True, window_fn=WINDOW_FN
    )

    # Truncate the nyquist frequency, commonly done in other papers,
    # also makes computation easier.
    magnitude = tf.abs(stft)[:, :, 0:-1]
    phase = tf.math.angle(stft)[:, :, 0:-1]

    if n_mel_bins:
        magnitude = _linear_to_mel_scale(
            magnitude, n_mel_bins, mel_lower_hertz_edge, mel_upper_hertz_edge
        )
        phase = _linear_to_mel_scale(
            phase, n_mel_bins, mel_lower_hertz_edge, mel_upper_hertz_edge
        )

    if log_magnitude:
        magnitude = tf.math.log(magnitude + _EPSILON)

    if instantaneous_frequency:
        phase = np.unwrap(phase)
        phase = np.concatenate([np.expand_dims(phase[:, 0, :], axis=-2),
                                np.diff(phase, axis=-2)], axis=-2).astype(np.float32)

    spectogram = tf.concat([tf.expand_dims(magnitude, 3),
                            tf.expand_dims(phase, 3)], axis=-1)

    return spectogram

def waveform_2_magnitude(waveform, frame_length=512, frame_step=128, log_magnitude=True,
                         n_mel_bins=None, mel_lower_hertz_edge=0.0,
                         mel_upper_hertz_edge=8000.0):
    """Transform a Waveform to a Magnitude Spectrum.

    This function is a wrapper for waveform_2_spectogram and removes
    the phase component.

    Args:
        waveform: the signal to be transformed. Expected shape
            is [time], or [batch, time].
        frame_length: The length of each frame.
        frame_step: Time increment after each frame, i.e.
            overlap=frame_length - frame_step.
        log_magnitude: If true, the log-magnitude will be returned.
        n_mel_bins: If specified, a magnitude spectrum in the mel scale
            will be returned.
        mel_lower_hertz_edge: The minimum frequency to be included in the
            mel-spectogram
        mel_upper_hertz_edge: The highest frequency to be included in the
            mel-spectogram

    Returns:
        A magnitude spectrum representation of the input waveform. Shape
        is [-1, time_bins, frequency]
    """

    spectogram = waveform_2_spectogram(
        waveform, frame_length=frame_length, frame_step=frame_step,
        log_magnitude=log_magnitude, n_mel_bins=n_mel_bins,
        mel_lower_hertz_edge=mel_lower_hertz_edge,
        mel_upper_hertz_edge=mel_upper_hertz_edge
    )

    magnitude = spectogram[:, :, :, 0]
    return magnitude

def magnitude_2_waveform(magnitude, n_iter=16, frame_length=512,
                         frame_step=128, log_magnitude=True,
                         n_mel_bins=None, mel_lower_hertz_edge=0.0,
                         mel_upper_hertz_edge=8000.0):
    """Transform a Magnitude Spectrum to a Waveform.

    Uses the Griffin-Lim algorythm, via the librosa implementation.

    Args:
        magnitude: the magnitude spectrum to be transformed. Expected
            shape is [time, frequencies] or [batch, time, frequencies]
        n_iter: number of Griffin-Lim iterations to run.
        frame_length: The length of each frame.
        frame_step: Time increment after each frame, i.e.
            overlap=frame_length - frame_step.
        log_magnitude: If true, the log-magnitude will be assumed.
        n_mel_bins: If specified, a magnitude spectrum in the mel scale
            will be returned.
        mel_lower_hertz_edge: The minimum frequency to be included in the
            mel-spectogram
        mel_upper_hertz_edge: The highest frequency to be included in the
            mel-spectogram

    Returns:
        A waveform representation of the input magnitude spectrum
        where the phase has been estimated using Griffin-Lim. Shape is
        [-1, signal_length]
    """

    if len(magnitude.shape) == 2:
        magnitude = tf.expand_dims(magnitude, 0)

    if log_magnitude:
        magnitude = np.exp(magnitude) - _EPSILON

    if n_mel_bins:
        magnitude = _mel_to_linear_scale(
            magnitude, frame_length//2, mel_lower_hertz_edge, mel_upper_hertz_edge
        )

    # Set the nyquist frequency to zero (the band we earlier removed).
    # This is also commonly done in these other papers.
    magnitude = np.pad(magnitude, [[0, 0], [0, 0], [0, 1]])

    to_waveform = lambda m: griffinlim(
        np.transpose(m), n_iter=n_iter, win_length=frame_length,
        hop_length=frame_step, pad_mode='constant', center=False
    )

    return np.array(list(map(to_waveform, magnitude)))

def spectogram_2_waveform(spectogram, frame_length=512, frame_step=128,
                          log_magnitude=True, instantaneous_frequency=True,
                          n_mel_bins=None, mel_lower_hertz_edge=0.0,
                          mel_upper_hertz_edge=8000.0):
    """Transforms a Spectogram to a Waveform.

    Args:
        spectogram: the spectogram to be transformed. Expected shape
            is [time, frequencies, 2] or [batch, time, frequencies, 2]
        frame_length: The length of each frame.
        frame_step: Time increment after each frame, i.e.
            overlap=frame_length - frame_step.
        log_magnitude: If true, log-magnitude will be assumed.
        instantaneous_frequency: If true, it is assumed the input is
            instantaneous frequency and not phase.
        n_mel_bins: If specified, a magnitude spectrum in the mel scale
            will be returned.
        mel_lower_hertz_edge: The minimum frequency to be included in the
            mel-spectogram
        mel_upper_hertz_edge: The highest frequency to be included in the
            mel-spectogram

    Returns:
        A waveform representation of the input spectogram. Shape is
        [-1, signal_length].
    """

    if len(spectogram.shape) == 3:
        spectogram = tf.expand_dims(spectogram, 0)

    magnitude = spectogram[:, :, :, 0]
    phase = spectogram[:, :, :, 1]

    if n_mel_bins:
        magnitude = _mel_to_linear_scale(
            magnitude, frame_length//2, mel_lower_hertz_edge, mel_upper_hertz_edge
        )
        phase = _mel_to_linear_scale(
            phase, frame_length//2, mel_lower_hertz_edge, mel_upper_hertz_edge
        )

    if log_magnitude:
        magnitude = tf.math.exp(magnitude) - _EPSILON

    if instantaneous_frequency:
        phase = tf.cumsum(phase, axis=-2)
        phase = (phase + np.pi) % (2 * np.pi) - np.pi

    # Set the nyquist frequency to zero (the band we earlier removed).
    # This is also commonly done in these other papers.
    magnitude = tf.pad(magnitude, [[0, 0], [0, 0], [0, 1]], constant_values=0)
    phase = tf.pad(phase, [[0, 0], [0, 0], [0, 1]], constant_values=0)

    real = magnitude * tf.math.cos(phase)
    img = magnitude * tf.math.sin(phase)

    stft = tf.complex(real, img)
    inv_window_fn = tf.signal.inverse_stft_window_fn(frame_step, forward_window_fn=WINDOW_FN)
    waveform = tf.signal.inverse_stft(
        stft, frame_length=frame_length,
        frame_step=frame_step, window_fn=inv_window_fn
    )
    return waveform
