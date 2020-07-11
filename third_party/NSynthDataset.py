# pylint: skip-file

# Copyright 2020 The Magenta Authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

## Taken from the GANSynth GitHub Reposotory.
## https://github.com/magenta/magenta/blob/master/magenta/models/gansynth/lib/datasets.py
## Slight modifications to make it compadable with the current version of TensorFlow.

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function


import tensorflow as tf
import collections
import numpy as np

Counter = collections.Counter


class BaseDataset(object):
  """A base class for reading data from disk."""

  def __init__(self, path):
    self._train_data_path = path

  def provide_one_hot_labels(self, batch_size):
    """Provides one-hot labels."""
    raise NotImplementedError

  def provide_dataset(self):
    """Provides audio dataset."""
    raise NotImplementedError

  def get_pitch_counts(self):
    """Returns a dictionary {pitch value (int): count (int)}."""
    raise NotImplementedError

  def get_pitches(self, num_samples):
    """Returns pitch_counter for num_samples for given dataset."""
    all_pitches = []
    pitch_counts = self.get_pitch_counts()
    for k, v in pitch_counts.items():
      all_pitches.extend([k]*v)
    sample_pitches = np.random.choice(all_pitches, num_samples)
    pitch_counter = Counter(sample_pitches)
    return pitch_counter


class NSynthTFRecordDataset(BaseDataset):
  """A dataset for reading NSynth from a TFRecord file."""

  def _get_dataset_from_path(self):
    dataset = tf.data.TFRecordDataset(self._train_data_path)
    return dataset

  def provide_one_hot_labels(self, batch_size):
    """Provides one hot labels."""
    pitch_counts = self.get_pitch_counts()
    pitches = sorted(pitch_counts.keys())
    counts = [pitch_counts[p] for p in pitches]
    indices = tf.reshape(
        tf.multinomial(tf.log([tf.to_float(counts)]), batch_size), [batch_size])
    one_hot_labels = tf.one_hot(indices, depth=len(pitches))
    return one_hot_labels

  def provide_dataset(self):
    """Provides dataset (audio, labels) of nsynth."""
    length = 64000
    channels = 1

    pitch_counts = self.get_pitch_counts()
    pitches = sorted(pitch_counts.keys())
    label_index_table = tf.lookup.StaticVocabularyTable(
        tf.lookup.KeyValueTensorInitializer(
            keys=pitches,
            values=np.arange(len(pitches)),
            key_dtype=tf.int64,
            value_dtype=tf.int64),
        num_oov_buckets=1)

    def _parse_nsynth(record):
        """Parsing function for NSynth dataset."""
        features = {
            'pitch': tf.io.FixedLenFeature([1], dtype=tf.int64),
            'audio': tf.io.FixedLenFeature([length], dtype=tf.float32),
            'qualities': tf.io.FixedLenFeature([10], dtype=tf.int64),
            'instrument_source': tf.io.FixedLenFeature([1], dtype=tf.int64),
            'instrument_family': tf.io.FixedLenFeature([1], dtype=tf.int64),
        }

        example = tf.io.parse_single_example(record, features)
        wave, label = example['audio'], example['pitch']
        one_hot_label = tf.one_hot(
            label_index_table.lookup(label), depth=len(pitches))[0]
        return wave, one_hot_label, label, example['instrument_source'], example['instrument_family']

    dataset = self._get_dataset_from_path()
    dataset = dataset.map(_parse_nsynth, num_parallel_calls=4)

    # Filter just acoustic instruments (as in the paper)
    # (0=acoustic, 1=electronic, 2=synthetic)
    dataset = dataset.filter(lambda w, l, p, s, f: tf.equal(s, 0)[0])
    # Filter only guitar instrument
    dataset = dataset.filter(lambda w, l, p, s, f: tf.equal(f, 3)[0])
    # Filter just pitches 24-84
    dataset = dataset.filter(lambda w, l, p, s, f: tf.greater_equal(p, 24)[0])
    dataset = dataset.filter(lambda w, l, p, s, f: tf.less_equal(p, 84)[0])

    # Currently, we are only interested in the waveform. In addition,
    # we pad the waveform length to make it 2^16 samples long. This
    # simplifys the generator and only adds an additional 1536 samples. 
    dataset = dataset.map(lambda w, l, p, s, f: tf.pad(tf.reshape(w, (-1,)), [[0, 1536]]))
    
    return dataset

  def get_pitch_counts(self):
    pitch_counts = {
        24: 711,
        25: 720,
        26: 715,
        27: 725,
        28: 726,
        29: 723,
        30: 738,
        31: 829,
        32: 839,
        33: 840,
        34: 860,
        35: 870,
        36: 999,
        37: 1007,
        38: 1063,
        39: 1070,
        40: 1084,
        41: 1121,
        42: 1134,
        43: 1129,
        44: 1155,
        45: 1149,
        46: 1169,
        47: 1154,
        48: 1432,
        49: 1406,
        50: 1454,
        51: 1432,
        52: 1593,
        53: 1613,
        54: 1578,
        55: 1784,
        56: 1738,
        57: 1756,
        58: 1718,
        59: 1738,
        60: 1789,
        61: 1746,
        62: 1765,
        63: 1748,
        64: 1764,
        65: 1744,
        66: 1677,
        67: 1746,
        68: 1682,
        69: 1705,
        70: 1694,
        71: 1667,
        72: 1695,
        73: 1580,
        74: 1608,
        75: 1546,
        76: 1576,
        77: 1485,
        78: 1408,
        79: 1438,
        80: 1333,
        81: 1369,
        82: 1331,
        83: 1295,
        84: 1291
    }
    return pitch_counts