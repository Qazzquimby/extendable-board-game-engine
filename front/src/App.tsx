import { useState } from 'react';
import { LogEntry } from './types';
import PhaserComponent from './PhaserComponent';

function App() {
  const [log, setLog] = useState<LogEntry[]>([]);
  const [currentStep, setCurrentStep] = useState(0);

  const handleFileChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (file) {
      const reader = new FileReader();
      reader.onload = (e) => {
        try {
          const content = e.target?.result;
          if (typeof content === 'string') {
            const jsonLog = JSON.parse(content);
            if (Array.isArray(jsonLog)) {
                setLog(jsonLog);
                setCurrentStep(0);
            } else {
                alert("Log file is not a JSON array of log entries.");
            }
          }
        } catch (error) {
          console.error("Error parsing JSON log file:", error);
          alert("Failed to parse log file. Is it valid JSON?");
        }
      };
      reader.readAsText(file);
    }
  };

  const currentLogEntry = log[currentStep];
  const stateToRender = currentLogEntry?.before_state;

  return (
    <div>
      <h1>Game Log Visualizer</h1>
      <input type="file" accept=".json,.jsonl" onChange={handleFileChange} />
      {log.length > 0 && (
        <>
          <div>
            <button onClick={() => setCurrentStep(s => Math.max(0, s - 1))} disabled={currentStep === 0}>
              Previous
            </button>
            <span> Step {currentStep} / {log.length - 1} </span>
            <button onClick={() => setCurrentStep(s => Math.min(log.length - 1, s + 1))} disabled={currentStep === log.length - 1}>
              Next
            </button>
          </div>
          {currentLogEntry && (
            <div>
              <h3>Action</h3>
              <p>Actor: {currentLogEntry.action.actor} performing {currentLogEntry.action.ability} on {currentLogEntry.action.target}. Movement: "{currentLogEntry.action.movement_name}" to [{String(currentLogEntry.action.move_pos)}]</p>
            </div>
          )}
          {stateToRender && <PhaserComponent engineState={stateToRender} action={currentLogEntry?.action} />}
        </>
      )}
    </div>
  );
}

export default App;
