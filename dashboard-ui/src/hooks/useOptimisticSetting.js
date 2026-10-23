import { useState, useCallback, useEffect } from 'react';
import { useToast } from '../components/ToastContext';

/**
 * Hook for optimistic UI updates with automatic rollback on API error.
 * @param {any} initialValue - Initial state value
 * @param {Function} saveFn - Async function (newValue) => Promise<any>
 * @param {string} [errorMessage] - Custom error toast message
 */
export function useOptimisticSetting(initialValue, saveFn, errorMessage = 'Failed to update setting. Changes rolled back.') {
  const [value, setValue] = useState(initialValue);
  const [saving, setSaving] = useState(false);
  const toast = useToast();

  useEffect(() => {
    setValue(initialValue);
  }, [initialValue]);

  const update = useCallback(async (nextValue) => {
    const previous = value;
    setValue(nextValue);
    setSaving(true);

    try {
      if (saveFn) {
        await saveFn(nextValue);
      }
    } catch (err) {
      setValue(previous); // Rollback immediately
      const detail = err.response?.data?.error || err.message || errorMessage;
      if (toast) {
        toast(detail, 'error');
      }
    } finally {
      setSaving(false);
    }
  }, [value, saveFn, toast, errorMessage]);

  return [value, update, saving, setValue];
}

export default useOptimisticSetting;
