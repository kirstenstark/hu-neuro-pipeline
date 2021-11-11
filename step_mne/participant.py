from os import path

from mne import Epochs, events_from_annotations
from mne.io import read_raw_brainvision

from .helpers import (add_heog_veog, apply_montage, compute_evokeds,
                      compute_single_trials, correct_besa, correct_ica,
                      get_bads, read_log)
from .savers import (save_clean, save_df, save_epochs, save_evokeds,
                     save_montage)


def participant_pipeline(
    vhdr_file=None,
    log_file=None,
    ocular_correction='fastica',
    bad_channels='auto',
    skip_log_rows=None,
    skip_log_conditions=None,
    downsample_sfreq=None,
    veog_channels='auto',
    heog_channels='auto',
    montage='easycap-M1',
    highpass_freq=0.1,
    lowpass_freq=30.0,
    epochs_tmin=-0.5,
    epochs_tmax=1.5,
    baseline=(-0.2, 0.0),
    triggers=None,
    reject_peak_to_peak=200.0,
    reject_flat=1.0,
    components={'name': [], 'tmin': [], 'tmax': [], 'roi': []},
    condition_cols=None,
    clean_dir=None,
    epochs_dir=None,
    trials_dir=None,
    evokeds_dir=None,
    export_dir=None,
    to_df=True,
):

    # Backup input arguments for re-use
    config = locals()

    # Get participant ID from filename
    participant_id = path.basename(vhdr_file).split('.')[0]

    # Read raw data
    raw = read_raw_brainvision(vhdr_file, preload=True)

    # Downsample
    if downsample_sfreq is not None:
        orig_sfreq = raw.info['sfreq']
        downsample_sfreq = float(downsample_sfreq)
        print(f'Downsampling from {orig_sfreq} Hz to {downsample_sfreq} Hz')
        raw.resample(downsample_sfreq)

    # Add EOG channels
    raw = add_heog_veog(raw, heog_channels, veog_channels)

    # Apply custom or standard montage
    apply_montage(raw, montage)

    # Interpolate any bad channels
    if bad_channels is not None and bad_channels != 'auto':
        if isinstance(bad_channels, str):
            bad_channels = [bad_channels]
        raw.info['bads'] = raw.info['bads'] + bad_channels
        _ = raw.interpolate_bads()

    # Re-reference to common average
    _ = raw.set_eeg_reference('average')

    # Do ocular correction
    if ocular_correction is not None:
        if path.isfile(ocular_correction):
            correct_besa(raw, besa_file=ocular_correction)
        else:
            correct_ica(raw, method=ocular_correction)

    # Filtering
    _ = raw.filter(highpass_freq, lowpass_freq)

    # Save cleaned continuous data
    if clean_dir is not None:
        save_clean(raw, clean_dir, participant_id)

    # Determine events and the corresponding (selection of) triggers
    events, event_id = events_from_annotations(
        raw, regexp='Stimulus', verbose=False)
    if triggers is not None:
        triggers = {key: int(value) for key, value in triggers.items()}
        event_id = triggers

    # Epoching including baseline correction
    epochs = Epochs(raw, events, event_id, epochs_tmin, epochs_tmax, baseline,
                    preload=True)

    # Drop the last sample to produce a nice even number
    _ = epochs.crop(epochs_tmin, epochs_tmax, include_tmax=False)
    print(epochs)

    # Read behavioral log file
    epochs.metadata = read_log(log_file, skip_log_rows, skip_log_conditions)
    epochs.metadata.insert(0, column='participant_id', value=participant_id)

    # Get indices of bad epochs and channels
    bad_ixs, auto_channels = get_bads(epochs, reject_peak_to_peak, reject_flat)

    # Start over, repairing any (automatically deteced) bad channels
    if bad_channels == 'auto':
        if auto_channels != []:
            config['bad_channels'] = auto_channels
            trials, evokeds, evokeds_df, config = participant_pipeline(**config)
            return trials, evokeds, evokeds_df, config
        else:
            config['bad_channels'] = []

    # Add single trial mean ERP amplitudes to metadata
    trials = compute_single_trials(epochs, components, bad_ixs)

    # Save epochs as data frame and/or MNE object
    if epochs_dir is not None:
        save_epochs(epochs, epochs_dir, participant_id, to_df)

    # Save single trial behavioral and ERP data
    if trials_dir is not None:
        save_df(trials, trials_dir, participant_id, suffix='trials')

    # Save channel locations
    if export_dir is not None:
        save_montage(epochs, export_dir)

    # Compute evokeds
    evokeds, evokeds_df = compute_evokeds(
        epochs, condition_cols, bad_ixs, participant_id)

    # Save evokeds as data frame and/or MNE object
    if evokeds_dir is not None:
        save_evokeds(evokeds, evokeds_df, evokeds_dir, participant_id, to_df)

    return trials, evokeds, evokeds_df, config