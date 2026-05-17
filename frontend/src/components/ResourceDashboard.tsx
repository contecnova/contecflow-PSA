/**
 * Resource Dashboard Component
 * Shows team availability, load scoring, and team health
 */
import _React, { useState, useEffect } from 'react';
import { resourcesApi } from '../services/api';

interface LoadScoringRow {
  user_id: number;
  user_name: string;
  role: string;
  load_pct: number;
  capacity_hours: number;
  available_hours: number;
  status: 'overloaded' | 'at_capacity' | 'underutilized' | string;
}

interface TeamHealth {
  avg_load_pct: number;
  overloaded_count: number;
  at_capacity_count: number;
  total_users: number;
}

function toArray<T>(value: unknown): T[] {
  return Array.isArray(value) ? (value as T[]) : [];
}

const ResourceDashboard = () => {
  const [loadScoring, setLoadScoring] = useState<LoadScoringRow[]>([]);
  const [teamHealth, setTeamHealth] = useState<TeamHealth | null>(null);
  const [loading, setLoading] = useState(true);
  const [filterStatus, setFilterStatus] = useState<'all' | 'overloaded' | 'at_capacity' | 'underutilized'>('all');

  useEffect(() => {
    fetchData();
  }, []);

  const fetchData = async () => {
    setLoading(true);
    try {
      const [loadRes, healthRes] = await Promise.all([
        resourcesApi.loadScoring({}),
        resourcesApi.teamHealth({}),
      ]);
      setLoadScoring(toArray<LoadScoringRow>(loadRes.data));
      setTeamHealth((healthRes.data ?? null) as TeamHealth | null);
    } catch {
      // silently handled — component shows empty state
    } finally {
      setLoading(false);
    }
  };

  const getStatusColor = (status: LoadScoringRow['status']) => {
    switch (status) {
      case 'overloaded':
        return 'bg-red-100 text-red-800';
      case 'at_capacity':
        return 'bg-yellow-100 text-yellow-800';
      case 'underutilized':
        return 'bg-green-100 text-green-800';
      default:
        return 'bg-gray-100 text-gray-800';
    }
  };

  const getLoadColor = (load: number) => {
    if (load > 100) return 'text-red-600';
    if (load > 80) return 'text-yellow-600';
    return 'text-green-600';
  };

  const filteredUsers = loadScoring.filter((user) => {
    if (filterStatus === 'all') return true;
    return user.status === filterStatus;
  });

  if (loading) {
    return <div className="text-center py-8">Loading resource data...</div>;
  }

  return (
    <div className="space-y-6">
      {/* Team Health Summary */}
      {teamHealth && (
        <div className="grid grid-cols-4 gap-4">
          <div className="bg-blue-50 p-4 rounded-lg">
            <div className="text-2xl font-bold text-blue-600">
              {teamHealth.avg_load_pct.toFixed(1)}%
            </div>
            <div className="text-sm text-gray-600">Avg Load</div>
          </div>
          <div className="bg-red-50 p-4 rounded-lg">
            <div className="text-2xl font-bold text-red-600">
              {teamHealth.overloaded_count}
            </div>
            <div className="text-sm text-gray-600">Overloaded</div>
          </div>
          <div className="bg-yellow-50 p-4 rounded-lg">
            <div className="text-2xl font-bold text-yellow-600">
              {teamHealth.at_capacity_count}
            </div>
            <div className="text-sm text-gray-600">At Capacity</div>
          </div>
          <div className="bg-green-50 p-4 rounded-lg">
            <div className="text-2xl font-bold text-green-600">
              {teamHealth.total_users}
            </div>
            <div className="text-sm text-gray-600">Total Users</div>
          </div>
        </div>
      )}

      {/* Load Scoring Table */}
      <div className="bg-white rounded-lg shadow">
        <div className="p-4 border-b flex justify-between items-center">
          <h3 className="font-semibold">Resource Load Ranking</h3>
          <select
            value={filterStatus}
            onChange={(e) => setFilterStatus(e.target.value as 'all' | 'overloaded' | 'at_capacity' | 'underutilized')}
            className="px-3 py-1 border rounded text-sm"
          >
            <option value="all">All Users</option>
            <option value="overloaded">Overloaded</option>
            <option value="at_capacity">At Capacity</option>
            <option value="underutilized">Underutilized</option>
          </select>
        </div>

        <table className="w-full text-sm">
          <thead className="bg-gray-50 border-b">
            <tr>
              <th className="px-4 py-2 text-left">Name</th>
              <th className="px-4 py-2 text-left">Role</th>
              <th className="px-4 py-2 text-right">Load %</th>
              <th className="px-4 py-2 text-right">Capacity</th>
              <th className="px-4 py-2 text-right">Available</th>
              <th className="px-4 py-2 text-left">Status</th>
            </tr>
          </thead>
          <tbody>
            {filteredUsers.map((user, idx) => (
              <tr key={user.user_id} className={idx % 2 === 0 ? 'bg-gray-50' : ''}>
                <td className="px-4 py-2 font-medium">{user.user_name}</td>
                <td className="px-4 py-2 text-gray-600">{user.role}</td>
                <td className={`px-4 py-2 text-right font-semibold ${getLoadColor(user.load_pct)}`}>
                  {user.load_pct.toFixed(1)}%
                </td>
                <td className="px-4 py-2 text-right">{user.capacity_hours.toFixed(1)}h</td>
                <td className="px-4 py-2 text-right text-green-600">
                  {user.available_hours.toFixed(1)}h
                </td>
                <td className="px-4 py-2">
                  <span className={`px-2 py-1 rounded-full text-xs font-semibold ${getStatusColor(user.status)}`}>
                    {user.status.replace(/_/g, ' ')}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        {filteredUsers.length === 0 && (
          <div className="text-center py-6 text-gray-500">
            No users found with selected filter
          </div>
        )}
      </div>
    </div>
  );
};

export default ResourceDashboard;
