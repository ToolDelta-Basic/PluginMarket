<?php
header('Content-Type: application/json; charset=utf-8');

// ================= 配置区 =================
$DB_HOST = 'localhost';
$DB_NAME = 'crossserver';
$DB_USER = 'crossserver';         // 你的数据库用户名
$DB_PASS = 's4hsK2YPmrBHLHKt';     // 你的数据库密码
$VALID_KEY = "scdcrossservernklm88"; // ⚠️ 通信密钥，必须与插件端一致
// ==========================================


try {
    $pdo = new PDO("mysql:host=$DB_HOST;dbname=$DB_NAME;charset=utf8mb4", $DB_USER, $DB_PASS);
    $pdo->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);
} catch (PDOException $e) {
    die(json_encode(["success" => false, "message" => "DB Error"]));
}

$action = $_REQUEST['action'] ?? '';
$secret_key = $_REQUEST['secret_key'] ?? '';

if ($secret_key !== $VALID_KEY) die(json_encode(["success" => false, "message" => "Key Error"]));

if ($action === 'send') {
    $from = $_POST['from_server'] ?? '';
    $to = $_POST['to_server'] ?? '';
    $type = $_POST['type'] ?? 'message';
    $content = $_POST['content'] ?? '';
    $sender = $_POST['sender_name'] ?? 'Unknown';

    if (!$from || !$to || !$content) die(json_encode(["success" => false]));

    $stmt = $pdo->prepare("INSERT INTO cross_server_data (from_server, to_server, type, content, sender_name) VALUES (?, ?, ?, ?, ?)");
    $stmt->execute([$from, $to, $type, $content, $sender]);
    die(json_encode(["success" => true]));
} 
elseif ($action === 'receive') {
    $server_name = $_POST['server_name'] ?? '';
    if (!$server_name) die(json_encode(["success" => false]));

    // 获取所有发给本服且未读的数据
    $stmt = $pdo->prepare("SELECT * FROM cross_server_data WHERE to_server = ? AND status = 0 ORDER BY id ASC");
    $stmt->execute([$server_name]);
    $rows = $stmt->fetchAll(PDO::FETCH_ASSOC);

    // 标记为已读
    if ($rows) {
        $ids = array_column($rows, 'id');
        $placeholders = implode(',', array_fill(0, count($ids), '?'));
        $updateStmt = $pdo->prepare("UPDATE cross_server_data SET status = 1 WHERE id IN ($placeholders)");
        $updateStmt->execute($ids);
    }

    die(json_encode(["success" => true, "data" => $rows ?: []]));
} else {
    die(json_encode(["success" => false]));
}
?>