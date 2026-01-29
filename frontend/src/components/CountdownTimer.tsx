import { useEffect, useState } from "react";

const CountdownTimer = ({ seconds }: { seconds: number }) => {
  const [timeLeft, setTimeLeft] = useState(seconds);

  useEffect(() => {
    if (timeLeft <= 0) return;

    const timer = setInterval(() => {
      setTimeLeft((t) => t - 1);
    }, 1000);

    return () => clearInterval(timer);
  }, [timeLeft]);

  const minutes = Math.floor(timeLeft / 60);
  const secs = timeLeft % 60;

  return (
    <div className="text-center text-lg font-bold text-red-400">
      ⏱ {minutes}:{secs.toString().padStart(2, "0")}
    </div>
  );
};

export default CountdownTimer;
