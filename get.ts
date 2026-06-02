// 实现一个类型安全的深度取值函数，支持嵌套对象和数组路径
// 例如：get(obj, 'a.b[0].c') 返回 obj.a.b[0].c 的值

type Path = string;

// 解析路径，支持点号和方括号，例如 'a.b[0].c' => ['a', 'b', '0', 'c']
function parsePath(path: Path): (string | number)[] {
    const segments: (string | number)[] = [];
    // 正则匹配：点号分隔或方括号内的数字
    const regex = /([^.[\]]+)|\[(\d+)\]/g;
    let match: RegExpExecArray | null;
    while ((match = regex.exec(path)) !== null) {
        if (match[1] !== undefined) {
            segments.push(match[1]);
        } else if (match[2] !== undefined) {
            segments.push(parseInt(match[2], 10));
        }
    }
    return segments;
}

// 深度取值函数
function get<T = any>(obj: any, path: Path, defaultValue?: T): T | undefined {
    if (obj == null) {
        return defaultValue;
    }
    const segments = parsePath(path);
    let current: any = obj;
    for (const key of segments) {
        if (current == null || !(key in current)) {
            return defaultValue;
        }
        current = current[key];
    }
    return current !== undefined ? current : defaultValue;
}

// 导出供测试使用
export { get, parsePath };
