import { Link } from "react-router-dom";
import { useAuth } from "../hooks/useAuth";

const Navbar = () => {
  const { user, logout } = useAuth();

  return (
    <nav className="bg-gray-950 text-white px-6 py-4 flex justify-between items-center">
      <Link to="/dashboard" className="text-xl font-bold text-indigo-500">
        DevDuel ⚔️
      </Link>

      <div className="flex gap-6 items-center">
        <Link to="/leaderboard" className="hover:text-indigo-400">
          Leaderboard
        </Link>
        <Link to="/profile" className="hover:text-indigo-400">
          Profile
        </Link>

        {user && (
          <button
            onClick={logout}
            className="bg-red-500 hover:bg-red-600 px-4 py-1 rounded"
          >
            Logout
          </button>
        )}
      </div>
    </nav>
  );
};

export default Navbar;
