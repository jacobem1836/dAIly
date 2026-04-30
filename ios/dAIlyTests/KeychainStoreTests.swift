import XCTest
@testable import dAIly

final class KeychainStoreTests: XCTestCase {

    // Use an isolated service name so tests never touch production tokens
    private let store = KeychainStore(service: "com.daily.ios.tests")

    override func setUp() {
        super.setUp()
        // Clear all test keychain items before each test
        try? store.clearAll()
    }

    override func tearDown() {
        // Clean up after each test
        try? store.clearAll()
        super.tearDown()
    }

    // Test 1: save then load returns the saved value
    func testSaveAndLoad() throws {
        try store.save(key: "access_token", value: "jwt-abc")
        let loaded = store.load(key: "access_token")
        XCTAssertEqual(loaded, "jwt-abc")
    }

    // Test 2: loading a missing key returns nil (no throw)
    func testLoadMissingKeyReturnsNil() {
        let loaded = store.load(key: "missing_key_that_does_not_exist")
        XCTAssertNil(loaded)
    }

    // Test 3: delete then load returns nil
    func testDeleteRemovesItem() throws {
        try store.save(key: "access_token", value: "jwt-abc")
        try store.delete(key: "access_token")
        let loaded = store.load(key: "access_token")
        XCTAssertNil(loaded)
    }

    // Test 4: saving again overwrites existing value (no errSecDuplicateItem)
    func testSaveOverwritesExistingValue() throws {
        try store.save(key: "access_token", value: "old-jwt")
        try store.save(key: "access_token", value: "new-jwt")
        let loaded = store.load(key: "access_token")
        XCTAssertEqual(loaded, "new-jwt")
    }

    // Test 5: clearAll removes all items written with this service
    func testClearAllRemovesAllItems() throws {
        try store.save(key: "access_token", value: "jwt-abc")
        try store.save(key: "refresh_token", value: "refresh-xyz")
        try store.clearAll()
        XCTAssertNil(store.load(key: "access_token"))
        XCTAssertNil(store.load(key: "refresh_token"))
    }

    // Test 6: stored items use kSecAttrAccessibleWhenUnlocked
    // Verified by querying with the explicit accessibility attribute —
    // if the item was stored with a different accessibility, the query returns nil.
    func testStoredItemsUseWhenUnlockedAccessibility() throws {
        try store.save(key: "access_token", value: "jwt-abc")

        // Query with explicit kSecAttrAccessibleWhenUnlocked filter
        let query: [CFString: Any] = [
            kSecClass: kSecClassGenericPassword,
            kSecAttrService: "com.daily.ios.tests",
            kSecAttrAccount: "access_token",
            kSecAttrAccessible: kSecAttrAccessibleWhenUnlocked,
            kSecReturnData: true,
            kSecMatchLimit: kSecMatchLimitOne,
        ]
        var item: CFTypeRef?
        let status = SecItemCopyMatching(query as CFDictionary, &item)
        XCTAssertEqual(status, errSecSuccess, "Item not found with kSecAttrAccessibleWhenUnlocked — wrong accessibility used during save")
        guard let data = item as? Data, let value = String(data: data, encoding: .utf8) else {
            XCTFail("Retrieved item is not valid UTF-8 string data")
            return
        }
        XCTAssertEqual(value, "jwt-abc")
    }
}
