import 'package:flutter/material.dart';
import 'package:sit_position_mobile/services/stats_service.dart';

class AchievementsScreen extends StatefulWidget {
  final StatsService statsService;

  const AchievementsScreen({super.key, required this.statsService});

  @override
  State<AchievementsScreen> createState() => _AchievementsScreenState();
}

class _AchievementsScreenState extends State<AchievementsScreen> {
  List<AchievementData> _achievements = [];

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final data = await widget.statsService.getAchievements();
    setState(() => _achievements = data);
  }

  @override
  Widget build(BuildContext context) {
    final unlocked = _achievements.where((a) => a.unlocked).length;
    final total = _achievements.length;

    return Scaffold(
      appBar: AppBar(
        title: Text('成就 ($unlocked/$total)'),
        centerTitle: true,
        elevation: 0,
      ),
      body: _achievements.isEmpty
          ? const Center(child: CircularProgressIndicator())
          : RefreshIndicator(
              onRefresh: _load,
              child: ListView.builder(
                padding: const EdgeInsets.all(16),
                itemCount: _achievements.length,
                itemBuilder: (context, index) {
                  return _buildAchievementCard(_achievements[index]);
                },
              ),
            ),
    );
  }

  Widget _buildAchievementCard(AchievementData achievement) {
    final isUnlocked = achievement.unlocked;

    return Card(
      elevation: isUnlocked ? 3 : 1,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
      margin: const EdgeInsets.only(bottom: 12),
      child: Container(
        decoration: isUnlocked
            ? BoxDecoration(
                borderRadius: BorderRadius.circular(16),
                gradient: LinearGradient(
                  colors: [Colors.amber[50]!, Colors.orange[50]!],
                  begin: Alignment.topLeft,
                  end: Alignment.bottomRight,
                ),
              )
            : null,
        padding: const EdgeInsets.all(16),
        child: Row(
          children: [
            // 图标
            Container(
              width: 56,
              height: 56,
              decoration: BoxDecoration(
                color: isUnlocked ? Colors.amber[100] : Colors.grey[200],
                borderRadius: BorderRadius.circular(14),
              ),
              child: Center(
                child: Text(
                  isUnlocked ? achievement.icon : '🔒',
                  style: const TextStyle(fontSize: 28),
                ),
              ),
            ),
            const SizedBox(width: 16),
            // 文字
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    achievement.name,
                    style: TextStyle(
                      fontSize: 16,
                      fontWeight: FontWeight.bold,
                      color: isUnlocked ? Colors.black87 : Colors.grey[500],
                    ),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    achievement.description,
                    style: TextStyle(
                      fontSize: 13,
                      color: isUnlocked ? Colors.grey[700] : Colors.grey[400],
                    ),
                  ),
                  if (!isUnlocked && achievement.progress > 0) ...[
                    const SizedBox(height: 8),
                    ClipRRect(
                      borderRadius: BorderRadius.circular(4),
                      child: LinearProgressIndicator(
                        value: achievement.progress,
                        backgroundColor: Colors.grey[200],
                        color: Colors.blue[300],
                        minHeight: 6,
                      ),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      '${achievement.bestMinutes}/${achievement.targetMinutes}',
                      style: TextStyle(fontSize: 11, color: Colors.grey[500]),
                    ),
                  ],
                ],
              ),
            ),
            if (isUnlocked)
              const Icon(Icons.check_circle, color: Colors.amber, size: 28),
          ],
        ),
      ),
    );
  }
}
