import Foundation
import Combine

final class AppState: ObservableObject {
    @Published var isAuthenticated: Bool = false
}
