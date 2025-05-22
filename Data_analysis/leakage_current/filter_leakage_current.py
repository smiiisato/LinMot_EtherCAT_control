import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from scipy.signal import iirnotch, filtfilt, find_peaks, butter
import os

############ CHANGE HERE ############
USE_FFT = True  # True: FFTでピーク周波数を自動検出
CSV_FILE = 'data_leakage_current/LeakageCurrent_1.2kV_flip_0_1.csv'
NOTCH_Q = 30.0      # 品質係数（Q値）
NOTCH_NUM = 10       # ノッチフィルタの数（ピーク数）
CUTOFF_LP1 = 500.0   # ローパスフィルタのカットオフ周波数 [Hz]
CUTOFF_LP2 = 300.0   # ローパスフィルタのカットオフ周波数 [Hz]
LP_ORDER = 4        # ローパスフィルタの次数
#####################################

import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy.signal import butter, filtfilt, iirnotch, find_peaks

# --- ローパスフィルタ定義 ---
def apply_butter_lowpass_filter(data, cutoff, fs, order=4):
    nyq = 0.5 * fs
    norm_cutoff = cutoff / nyq
    b, a = butter(order, norm_cutoff, btype='low', analog=False)
    return filtfilt(b, a, data)

def plot_filtered_signal(time, original_signal, filtered_signal, title='Filtered Signal'):
    plt.figure(figsize=(10, 5))
    plt.plot(time * 1000, original_signal, label='Original', alpha=0.7)
    plt.plot(time * 1000, filtered_signal, label='Filtered', linewidth=2)
    plt.xlabel('Time [ms]')
    plt.ylabel('Current [uA]')
    plt.title(title)
    plt.legend()
    plt.grid(True)
    plt.tight_layout()
    plt.show()

def fft_analysis(signal, dt, peak_num=5):
    N = len(signal)
    fft_vals = np.fft.fft(signal)
    fft_freqs = np.fft.fftfreq(N, d=dt)
    amplitude = np.abs(fft_vals)

    # 正の周波数だけ取得（DC除外）
    pos_mask = (fft_freqs > 1)
    pos_freqs = fft_freqs[pos_mask]
    pos_amplitude = amplitude[pos_mask]

    # ピーク検出
    peak_indices, properties = find_peaks(pos_amplitude, height=np.max(pos_amplitude) * 0.1)
    peak_freqs = pos_freqs[peak_indices]
    peak_heights = properties['peak_heights']

    # 上位 N 個のピーク周波数を取得
    if len(peak_freqs) >= peak_num:
        top_indices = np.argsort(peak_heights)[-peak_num:]
    else:
        top_indices = np.argsort(peak_heights)

    top_peak_freqs = peak_freqs[top_indices]
    top_peak_heights = peak_heights[top_indices]

    return pos_freqs, pos_amplitude, peak_freqs, peak_heights, top_peak_freqs, top_peak_heights

def plot_fft_signal(pos_freqs, pos_amplitude, peak_freqs, peak_heights, top_peak_freqs, top_peak_heights, cutoff_freq, peak_num=5, title='FFT Signal'):
    plt.figure(figsize=(10, 5))
    plt.plot(pos_freqs, pos_amplitude)
    plt.scatter(top_peak_freqs, top_peak_heights, color='red', label='Detected Peaks')
    plt.xlabel('Frequency [Hz]')
    plt.ylabel('Amplitude')
    plt.xlim(0, cutoff_freq * 2)
    plt.title(title)
    plt.grid(True)
    plt.tight_layout()
    plt.show()

def apply_notch_filter(signal, f0, Q, fs):
    b, a = iirnotch(f0, Q, fs)
    return filtfilt(b, a, signal)

def apply_moving_average_filter(signal, window_size):
    return np.convolve(signal, np.ones(window_size)/window_size, mode='same')


def main():
    # CSV読み込み
    df = pd.read_csv(os.path.join(os.path.dirname(__file__), CSV_FILE))

    # 時間・電流信号取得
    time = df['Time(s)'].values
    current_uA = df['Current(uA)'].values

    # サンプリング周波数の計算
    dt = np.mean(np.diff(time))
    fs = 1 / dt

    pos_freqs, pos_amplitude, peak_freqs, peak_heights, top_peak_freqs, top_indices = fft_analysis(current_uA, dt, peak_num=NOTCH_NUM)
    plot_fft_signal(pos_freqs, pos_amplitude, peak_freqs, peak_heights, top_peak_freqs, top_indices, CUTOFF_LP1, peak_num=NOTCH_NUM, title='FFT Signal before Filtering')

    # --- 最初のローパスフィルタ ---
    current_lp1 = apply_butter_lowpass_filter(current_uA, CUTOFF_LP1, fs, order=LP_ORDER)
    plot_filtered_signal(time, current_uA, current_lp1, title='Filtered Signal after First Lowpass Filter')

    # --- ノッチフィルタの準備と適用 ---
    filtered_current = current_lp1.copy()

    if USE_FFT:
        # ===== First Notch Filter =====
        pos_freqs, pos_amplitude, peak_freqs, peak_heights, top_peak_freqs, top_indices = fft_analysis(filtered_current, dt, peak_num=NOTCH_NUM)
        plot_fft_signal(pos_freqs, pos_amplitude, peak_freqs, peak_heights, top_peak_freqs, top_indices, CUTOFF_LP1, peak_num=NOTCH_NUM, title='FFT Signal after First Lowpass Filter')

        print(f"Top {len(top_peak_freqs)} peak frequencies to apply notch filters: {top_peak_freqs}")

        # --- ノッチフィルタの適用 ---
        for f0 in top_peak_freqs:
            filtered_current = apply_notch_filter(filtered_current, f0, NOTCH_Q, fs)

        # --- フィルタ後のFFT表示 ---
        pos_freqs, pos_amplitude, _, _, top_peak_freqs, top_indices = fft_analysis(filtered_current, dt, peak_num=NOTCH_NUM)
        plot_fft_signal(pos_freqs, pos_amplitude, [], [], top_peak_freqs, top_indices, CUTOFF_LP1, peak_num=NOTCH_NUM, title='FFT Signal after first Notch Filter')

        plot_filtered_signal(time, current_uA, filtered_current, title='Filtered Signal after First Notch Filter')

        # ===== Second Notch Filter =====
        """ pos_freqs, pos_amplitude, peak_freqs, peak_heights, top_peak_freqs, top_indices = fft_analysis(filtered_current, dt, peak_num=NOTCH_NUM)
        plot_fft_signal(pos_freqs, pos_amplitude, peak_freqs, peak_heights, top_peak_freqs, top_indices, CUTOFF_LP1, peak_num=NOTCH_NUM, title='FFT Signal after First Notch Filter') """
        print(f"Top {len(top_peak_freqs)} peak frequencies to apply notch filters: {top_peak_freqs}")
        # --- ノッチフィルタの適用 ---
        for f0 in top_peak_freqs:
            b, a = iirnotch(f0, NOTCH_Q, fs)
            filtered_current = filtfilt(b, a, filtered_current)
        
        # --- フィルタ後のFFT表示 ---
        pos_freqs, pos_amplitude, _, _, top_peak_freqs, top_indices = fft_analysis(filtered_current, dt, peak_num=NOTCH_NUM)
        plot_fft_signal(pos_freqs, pos_amplitude, [], [], top_peak_freqs, top_indices, CUTOFF_LP1, peak_num=NOTCH_NUM, title='FFT Signal after Second Notch Filter')
        # --- フィルタ後の信号プロット ---
        plot_filtered_signal(time, current_uA, filtered_current, title='Filtered Signal after Second Notch Filter')
        

        # --- 最後のローパスフィルタ ---
        filtered_current = apply_butter_lowpass_filter(filtered_current, CUTOFF_LP2, fs, order=LP_ORDER)
        #filtered_current = apply_moving_average_filter(filtered_current, window_size=50)

        # --- フィルタ後のFFT表示 ---
        pos_freqs, pos_amplitude, _, _, top_peak_freqs, top_indices = fft_analysis(filtered_current, dt, peak_num=NOTCH_NUM)
        plot_fft_signal(pos_freqs, pos_amplitude, [], [], top_peak_freqs, top_indices, CUTOFF_LP2, peak_num=NOTCH_NUM, title='FFT Signal after Second Lowpass Filter')

        # --- 結果のプロット ---
        plot_filtered_signal(time, current_uA, filtered_current, title='Filtered Signal after Second Lowpass Filter')


if __name__ == "__main__":
    main()
