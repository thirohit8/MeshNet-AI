/**
 * signal.ts — Signal-flicker event model
 * backend/src/models/signal.ts
 *
 * Describes a single observation of a node's signal level and the
 * derived flicker-alert that fires the high-priority data burst.
 */

/**
 * A raw signal sample submitted by a device's heartbeat or the
 * Python signal monitor via POST /api/signal/report.
 */
export interface SignalSample {
  nodeId:    string;   // device that measured the signal
  nodeLabel: string;
  signal:    number;   // 0–100 RSSI-normalised
  scenario:  string;   // flood | war_zone | earthquake
  timestamp: string;   // ISO-8601
}

/**
 * A signal-flicker event persisted to the signal_events table.
 * Created the instant a node transitions from 0 → ≥1 signal bar.
 */
export interface SignalFlickerEvent {
  id:          string;
  nodeId:      string;
  nodeLabel:   string;
  prevSignal:  number;   // signal just before the flicker (was 0 or below threshold)
  currSignal:  number;   // signal after the flicker (now ≥ threshold)
  scenario:    string;
  burst:       boolean;  // true once the high-priority burst has been dispatched
  detectedAt:  string;   // ISO-8601
}
