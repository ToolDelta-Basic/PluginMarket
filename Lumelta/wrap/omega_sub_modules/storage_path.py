import os
import shutil
class StoragePath:
    """存储路径管理类"""
    def __init__(self, omega):
        self.omega = omega
    
    # ========== 路径获取方法 ==========
    def get_config_path(self, *args):
        """获取配置文件路径"""
        return os.path.join(self.omega.config_dir_path, *args)
    
    def get_code_path(self, *args):
        """获取代码文件路径"""
        return os.path.join(self.omega.code_dir_path, *args)
    
    def get_data_file_path(self, *args):
        """获取数据文件路径"""
        return os.path.join(self.omega.data_dir_path, *args)
    
    def get_cache_path(self, *args):
        """获取缓存文件路径"""
        return os.path.join(self.omega.cache_dir_path, *args)
    
    # ========== 路径操作方法 ==========
    def list_dir(self, path):
        """列出目录内容"""
        try:
            return os.listdir(path), None
        except Exception as e:
            return None, str(e)
    
    def abs(self, path):
        """获取绝对路径"""
        return os.path.abspath(path)
    
    def join(self, *args):
        """路径拼接"""
        return os.path.join(*args)
    
    def ext(self, path):
        """获取文件扩展名"""
        return os.path.splitext(path)[1] or ""  # 处理无扩展名情况
    
    def move(self, src, dst):
        """移动文件/目录"""
        shutil.move(src, dst)
    
    def remove(self, path):
        """删除文件/目录"""
        if os.path.isfile(path) or os.path.islink(path):
            os.remove(path)
        elif os.path.isdir(path):
            shutil.rmtree(path)
        else:
            raise FileNotFoundError(f"路径不存在: {path}")
    
    def exist(self, path):
        """判断路径是否存在"""
        return os.path.exists(path)
