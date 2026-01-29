interface MatchFoundModalProps {
  visible: boolean;
  opponent: string;
  onAccept: () => void;
}

const MatchFoundModal = ({
  visible,
  opponent,
  onAccept,
}: MatchFoundModalProps) => {
  if (!visible) return null;

  return (
    <div className="fixed inset-0 bg-black bg-opacity-70 flex items-center justify-center z-50">
      <div className="bg-gray-900 text-white p-6 rounded-xl w-80 text-center">
        <h2 className="text-xl font-bold mb-3">Match Found ⚔️</h2>
        <p className="mb-4">Opponent: <span className="font-semibold">{opponent}</span></p>

        <button
          onClick={onAccept}
          className="bg-green-600 hover:bg-green-700 px-4 py-2 rounded w-full"
        >
          Accept Duel
        </button>
      </div>
    </div>
  );
};

export default MatchFoundModal;
