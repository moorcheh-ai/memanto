// 测试文件: test/index.test.ts
import { sortAndDeduplicate } from '../src/index';

describe('sortAndDeduplicate', () => {
    it('should sort and deduplicate an array of strings', () => {
        const input = ['banana', 'apple', 'cherry', 'apple', 'date'];
        const expected = ['apple', 'banana', 'cherry', 'date'];
        expect(sortAndDeduplicate(input)).toEqual(expected);
    });

    it('should handle empty array', () => {
        expect(sortAndDeduplicate([])).toEqual([]);
    });

    it('should handle array with one element', () => {
        expect(sortAndDeduplicate(['single'])).toEqual(['single']);
    });

    it('should throw error for non-array input', () => {
        expect(() => sortAndDeduplicate('not an array' as any)).toThrow('Input must be an array');
    });

    it('should handle array with duplicates only', () => {
        const input = ['a', 'a', 'a'];
        expect(sortAndDeduplicate(input)).toEqual(['a']);
    });
});