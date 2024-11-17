import numpy as np
import pandas as pd
import torch
from torch.utils.data import Dataset, DataLoader

class TimeSeriesDataset(Dataset):
    def __init__(self, data, value_col='Value', time_col='Time', 
                 interval_value=5, interval_unit='s', interpolation_limit=11,
                 kernel_size=512, stride=512, missing_thresh=0.5):
        self.data = data
        self.value_col = value_col
        self.time_col = time_col
        self.data[self.time_col] = pd.to_datetime(self.data[self.time_col])
        self.data = self._construct_dataset(interval_value, interval_unit, interpolation_limit)

        self.seqs = []
        self.masks = []
        self.times = []
        self._create_seq(kernel_size, stride, missing_thresh)

    def _construct_dataset(self, interval_value, interval_unit, interpolation_limit):
        '''Reindexes data using pd.date_range with a frequency of interval_value interval_unit.
        Interpolates data with a limit of interpolation_limit'''
        df = self.data.copy()
        df = df.set_index(self.time_col)
        
        # Create time index with interval
        min_time = df.index.min()
        max_time = df.index.max()
        new_time_index = pd.date_range(min_time, max_time, freq=str(interval_value)+interval_unit)

        # Reindex with new time index
        reindex_df = df.reindex(new_time_index, method='nearest', tolerance=pd.Timedelta(interval_value-1, unit=interval_unit))

        # Reset index
        reindex_df.reset_index(inplace=True)
        reindex_df.rename(columns={'index': self.time_col}, inplace=True)

        return reindex_df.reset_index(drop=True).interpolate(limit=interpolation_limit)
    
    def _create_seq(self, kernel_size, stride, missing_thresh):
        df = self.data
        data_len = len(df)
        for i in range(0, data_len, stride):
            seq = df[self.value_col][i:i+kernel_size]
            time = df[self.time_col][i:i+kernel_size]
            if seq.isna().mean() <= missing_thresh:
                self.seqs.append(np.array(seq))
                self.masks.append(np.array(seq.notna()))
                self.times.extend(list(time))

    def __len__(self):
        return len(self.seqs)
    
    def __getitem__(self, idx):
        seq = torch.tensor(self.seqs[idx], dtype=torch.float32)
        return seq, self.masks[idx]
    

def get_anomalies(data, model, anomaly_thresh=20):
    dataset = TimeSeriesDataset(data)
    batch_size = dataset.__len__() - 1
    dataloader = DataLoader(dataset, batch_size=batch_size, drop_last=True)
    x, mask = next(iter(dataloader))
    x = x[:, None, :]

    with torch.no_grad():
        output = model(x_enc=x, input_mask=mask)

    preds = output.reconstruction.squeeze().numpy().flatten().astype('float64')
    trues = x.squeeze().numpy().flatten().astype('float64')
    anomaly_scores = np.abs(trues - preds) / preds * 100

    anomalies = pd.DataFrame({'Time': dataset.times[:len(trues)],
                              'Recorded': trues.round(1), 
                              'Predicted': preds.round(1), 
                              'Anomaly Score': anomaly_scores.round(1)})
    return anomalies.loc[anomalies['Anomaly Score'] > anomaly_thresh]