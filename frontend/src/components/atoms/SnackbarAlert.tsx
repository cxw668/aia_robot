import { Snackbar, Alert, type AlertColor } from '@mui/material';

interface Props {
  open: boolean;
  message: string;
  severity?: AlertColor;
  onClose: () => void;
  duration?: number;
}

export default function SnackbarAlert({
  open,
  message,
  severity = 'success',
  onClose,
  duration = 3000,
}: Props) {
  return (
    <Snackbar
      open={open}
      autoHideDuration={duration}
      onClose={onClose}
      anchorOrigin={{ vertical: 'top', horizontal: 'center' }}
    >
      <Alert
        onClose={onClose}
        severity={severity}
        variant="filled"
        sx={{ width: '100%', borderRadius: 2 }}
      >
        {message}
      </Alert>
    </Snackbar>
  );
}
