// @ts-nocheck
/**
 * toastError(message)
 *
 * Mostra un toast di errore con pulsante "Copia" che copia il messaggio negli appunti.
 * Usa Sonner toast.error con action personalizzata.
 */
import { toast } from 'sonner';

export function toastError(message) {
  const text = typeof message === 'string' ? message : String(message ?? 'Unknown error');
  toast.error(text, {
    duration: 8000,
    action: {
      label: 'Copy',
      onClick: () => {
        navigator.clipboard.writeText(text).then(() => {
          toast.success('Error copied to clipboard', { duration: 2000 });
        });
      },
    },
  });
}
