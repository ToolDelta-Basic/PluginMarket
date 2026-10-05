<?php
header('Content-Type: application/json; charset=utf-8');

//配置区
$VALID_KEY = "scdcrossservernklm88"; //通信密钥(必须与插件端一致)
$DATA_FILE = __DIR__ . '/cross_server_data.json'; //数据文件(自动生成)

$action = $_REQUEST['action'] ?? '';
$secret_key = $_REQUEST['secret_key'] ?? '';

//密钥验证
if ($secret_key !== $VALID_KEY) {
    die(json_encode(["success" => false, "message" => "Key Error"]));
}

function atomic_update($file, $callback) {
    if (!file_exists($file)) {
        file_put_contents($file, '[]');
    }
    
    $fp = fopen($file, 'c+');
    if (!$fp) return ["success" => false, "message" => "Cannot open file"];
    
    if (!flock($fp, LOCK_EX)) {
        fclose($fp);
        return ["success" => false, "message" => "Cannot lock file"];
    }
    
    $content = stream_get_contents($fp);
    $data = json_decode($content, true);
    if (!is_array($data)) $data = [];
    
    $result = $callback($data);
    
    //清空文件并重新写入
    ftruncate($fp, 0);
    rewind($fp);
    fwrite($fp, json_encode($data, JSON_UNESCAPED_UNICODE));
    fflush($fp);
    
    flock($fp, LOCK_UN);
    fclose($fp);
    
    return $result;
}

//发送消息
if ($action === 'send') {
    $from = $_POST['from_server'] ?? '';
    $to = $_POST['to_server'] ?? '';
    $type = $_POST['type'] ?? 'message';
    $content = $_POST['content'] ?? '';
    $sender = $_POST['sender_name'] ?? 'Unknown';

    if (!$from || !$to || !$content) die(json_encode(["success" => false]));

    $result = atomic_update($DATA_FILE, function(&$data) use ($from, $to, $type, $content, $sender) {
        //生成自增ID
        $max_id = 0;
        foreach ($data as $row) {
            if (isset($row['id']) && $row['id'] > $max_id) $max_id = $row['id'];
        }
        
        $data[] = [
            'id' => $max_id + 1,
            'from_server' => $from,
            'to_server' => $to,
            'type' => $type,
            'content' => $content,
            'sender_name' => $sender,
            'status' => 0,
            'created_at' => date('Y-m-d H:i:s')
        ];
        
        //自动清理:防止文件无限增大 当记录超过 2000 条时 自动删除已读的旧消息
        if (count($data) > 2000) {
            $data = array_values(array_filter($data, function($row) {
                return $row['status'] == 0; //仅保留未读消息
            }));
        }
        
        return ["success" => true];
    });
    die(json_encode($result));
} 

//接收消息
elseif ($action === 'receive') {
    $server_name = $_POST['server_name'] ?? '';
    if (!$server_name) die(json_encode(["success" => false]));

    $result = atomic_update($DATA_FILE, function(&$data) use ($server_name) {
        $unread_messages = [];
        
        //遍历并标记已读
        foreach ($data as &$row) {
            if ($row['to_server'] === $server_name && $row['status'] == 0) {
                $unread_messages[] = $row;
                $row['status'] = 1; //标记为已读
            }
        }
        
        return ["success" => true, "data" => $unread_messages];
    });
    die(json_encode($result));
} 

else {
    die(json_encode(["success" => false, "message" => "Invalid action"]));
}
?>