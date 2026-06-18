import pandas as pd
import numpy as np

df = pd.read_csv(r'C:\Users\LENOVO\Documents\routing-project\module2_mahemobility\data\cell_towers.csv')

np.random.seed(42)
operators = np.random.choice(
    ['Jio', 'Airtel', 'Vi', 'BSNL'],
    size=len(df),
    p=[0.40, 0.30, 0.20, 0.10]
)

mnc_map = {'Jio': 472, 'Airtel': 10, 'Vi': 20, 'BSNL': 1}
df['net'] = [mnc_map[op] for op in operators]

df.to_csv(r'C:\Users\LENOVO\Documents\routing-project\module2_mahemobility\data\cell_towers.csv', index=False)
print('Done. Operator distribution:')
print(pd.Series(operators).value_counts())