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

"""Pre-Processes the MAESTRO Dataset.

Pre-proceses the raw MAESTRO dataset into a data set
of music chunks with a predefined lenth and sampling rate.
The music chunks are then saved as a .npz file
"""

import sys
import glob
import librosa
import numpy as np

# Overall Config #
APPROX_TOTAL_HOURS = 6
SAMPLE_RATE = 16000 # 16kHz
DATA_POINT_LENGTH = 2**14
RAW_DATA_PATH = './data/maestro/2017'
PROCESSED_DATA_PATH = '../data/'


if __name__ == '__main__':
    audio_paths = glob.glob(RAW_DATA_PATH + '/**/*.wav', recursive=True)

    # Load audio files until we reach our desired
    # data set size.
    data = []
    hours_loaded = 0 # pylint: disable=invalid-name
    for file in audio_paths:
        print(file)
        wav, _ = librosa.load(file, sr=SAMPLE_RATE)

        hours_loaded += len(wav) / SAMPLE_RATE / 60 / 60
        if hours_loaded >= APPROX_TOTAL_HOURS:
            break

        # Pad the song to ensure it can be evenly divided into
        # chunks of length 'DATA_POINT_LENGTH'
        padded_wav_length = int(DATA_POINT_LENGTH * np.ceil(len(wav) / DATA_POINT_LENGTH))
        wav = np.pad(wav, [[0, padded_wav_length - len(wav)]])

        chunks = np.reshape(wav, (-1, DATA_POINT_LENGTH))
        data.extend(chunks)

    data = np.array(data)

    print('Dataset Stats:')
    print('Total Hours: ', len(data) / 60 / 60)
    print('Dataset Size: ', sys.getsizeof(data) / 1e9, 'GB')
    print('Dataset Shape: ', data.shape)

    print("Saving Waveform Dataset")
    np.savez_compressed(PROCESSED_DATA_PATH + 'MAESTRO_'\
                        + str(APPROX_TOTAL_HOURS) + 'h.npz',
                        np.array(data))