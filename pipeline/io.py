import json
from os import makedirs

import pandas as pd
from mne import Report, write_evokeds


def check_participant_input(input, participant_ids):
    """Converts different inputs (e.g., dict) into a per-participant list."""

    # If it's a dict, convert to list
    if isinstance(input, dict):
        participant_dict = {id: None for id in participant_ids}
        for id, values in input.items():
            assert id in participant_ids, \
                f'Participant ID {id} is not in vhdr_files'
            participant_dict[id] = values
        return participant_dict.values()

    # If it's a list of list, it must have the same length as participant_ids
    elif is_nested_list(input):
        assert len(input) == len(participant_ids), \
            'Input lists must have the same length'
        return input

    # Otherwise all participants get the same values
    else:
        return [input] * len(participant_ids)


def is_nested_list(input):
    """Checks if a list is nested, i.e., contains at least one other list."""

    # Check if there is any list in the list
    if isinstance(input, list):
        return any(isinstance(elem, list) for elem in input)
    else:
        return False


def save_clean(raw, output_dir, participant_id=''):
    """Saves cleaned (continuous) EEG data in `.fif` format."""

    # Re-format participant ID for filename
    participant_id_ = '' if participant_id == '' else f'{participant_id}_'
    suffix = 'cleaned_eeg'

    # Create output folder and save
    makedirs(output_dir, exist_ok=True)
    fname = f'{output_dir}/{participant_id_}{suffix}.fif'
    raw.save(fname)


def save_df(df, output_dir, participant_id='', suffix=''):
    """Saves pd.DataFrame in `.csv` format."""

    # Create output folder
    makedirs(output_dir, exist_ok=True)

    # Re-format participant ID and suffix for filename
    participant_id_ = '' if participant_id == '' else f'{participant_id}_'
    suffix = '' if suffix == '' else suffix

    # Save DataFrame
    fname = f'{output_dir}/{participant_id_}{suffix}.csv'
    df.to_csv(
        fname, na_rep='NA', float_format='%.4f', index=False)


def save_epochs(epochs, output_dir, participant_id='', to_df=True):
    """Saves mne.Epochs with metadata in `.fif` and/or `.csv` format."""

    # Create output folder
    makedirs(output_dir, exist_ok=True)

    # Re-format participant ID for filename
    participant_id_ = '' if participant_id == '' else f'{participant_id}_'
    suffix = 'epo'

    # Convert to DataFrame
    if to_df is True or to_df == 'both':
        scalings = {'eeg': 1e6, 'misc': 1e6}
        epochs_df = epochs.to_data_frame(scalings=scalings)

        # Add metadata from log file
        metadata_df = epochs.metadata.copy()
        metadata_df = metadata_df.drop([col for col in metadata_df.columns
                                        if col in epochs_df.columns], axis=1)
        n_samples = len(epochs.times)
        metadata_df = metadata_df.loc[metadata_df.index.repeat(n_samples)]
        metadata_df = metadata_df.reset_index(drop=True)
        epochs_df = pd.concat([metadata_df, epochs_df], axis=1)

        # Save DataFrame
        save_df(epochs_df, output_dir, participant_id, suffix)

    # Save as MNE object
    if to_df is False or to_df == 'both':
        fname = f'{output_dir}/{participant_id_}{suffix}.fif'
        epochs.save(fname, overwrite=True)


def save_evokeds(
        evokeds, evokeds_df, output_dir, participant_id='', to_df=True):
    """Saves a list of mne.Evokeds in `.fif` and/or `.csv` format."""

    # Re-format participant ID for filename
    participant_id_ = '' if participant_id == '' else f'{participant_id}_'
    suffix = 'ave'

    # Create output directory
    makedirs(output_dir, exist_ok=True)

    # Save evokeds as DataFrame
    if to_df is True or to_df == 'both':
        save_df(evokeds_df, output_dir, participant_id, suffix)

    # Save evokeds as MNE object
    if to_df is False or to_df == 'both':
        fname = f'{output_dir}/{participant_id_}{suffix}.fif'
        write_evokeds(fname, evokeds, verbose=False)


def save_montage(epochs, output_dir):
    """Saves channel locations in `.csv` format."""

    # Create output directory
    makedirs(output_dir, exist_ok=True)

    # Get locations of EEG channels
    chs = epochs.copy().pick_types(eeg=True).info['chs']
    coords = [ch['loc'][0:3] for ch in chs]
    coords_df = pd.DataFrame(columns=['x', 'y', 'z'], data=coords)

    # Add channel names
    ch_names = [ch['ch_name'] for ch in chs]
    coords_df.insert(loc=0, column='ch_name', value=ch_names)

    # Save
    save_df(coords_df, output_dir, suffix='channel_locations')


def save_config(config, output_dir):
    """Saves dict of pipeline config options in `.json` format."""

    # Create output directory
    makedirs(output_dir, exist_ok=True)

    # Save
    fname = f'{output_dir}/config.json'
    with open(fname, 'w') as f:
        json.dump(config, f)


def save_report(raw, ica, clean, events, event_id, epochs, evokeds, output_dir,
                participant_id):
    """Saves HTML report."""

    # Initialize HTML report
    report = Report(title=f'Report for {participant_id}', verbose=False)

    # Add raw data
    report.add_raw(raw, title='Raw data')

    # Add ICA
    if ica is not None:
        report.add_ica(ica, title='ICA', inst=raw)

    # Add cleaned data
    report.add_raw(clean, title='Cleaned data')

    # Add events
    sfreq = clean.info['sfreq']
    report.add_events(
        events, title='Event triggers', event_id=event_id, sfreq=sfreq)

    # Add epochs
    report.add_epochs(epochs, title='Epochs')

    # Add evokeds
    report.add_evokeds(evokeds)  # Automatically uses comments as titles

    # Create output directory
    makedirs(output_dir, exist_ok=True)

    # Save
    fname = f'{output_dir}/{participant_id}_report.html'
    print(f'Saving HTML report to {fname}\n')
    _ = report.save(fname, open_browser=False, overwrite=True)