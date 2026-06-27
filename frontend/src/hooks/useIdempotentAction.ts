import { useRef, useState, useCallback } from "react";

/**
 * Wraps an async action with a synchronous ref-based guard to prevent
 * duplicate concurrent executions. Immune to React's batched state updates.
 *
 * Usage:
 *   const [execute, isRunning] = useIdempotentAction(myAsyncFn);
 *   <button onClick={execute} disabled={isRunning}>Go</button>
 */
export function useIdempotentAction<Args extends unknown[], T>(
  action: (...args: Args) => Promise<T>
): [(...args: Args) => Promise<T | undefined>, boolean] {
  const inFlightRef = useRef(false);
  const [isRunning, setIsRunning] = useState(false);

  const execute = useCallback(
    async (...args: Args): Promise<T | undefined> => {
      // Synchronous check — immune to React's batched state updates
      if (inFlightRef.current) return undefined;
      inFlightRef.current = true;
      setIsRunning(true);
      try {
        return await action(...args);
      } finally {
        inFlightRef.current = false;
        setIsRunning(false);
      }
    },
    [action]
  );

  return [execute, isRunning];
}
