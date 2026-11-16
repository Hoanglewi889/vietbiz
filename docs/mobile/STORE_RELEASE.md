# VietBiz trên App Store và Google Play — các bước

Viết ngày 16.11.2026 theo quyết định của chủ dự án: app làm bằng **Capacitor bọc workspace web**,
đăng nhập **email + mã một lần (OTP)** qua máy chủ đăng nhập OIDC, **chưa có tài khoản nhà phát
triển** (chuẩn bị trước), **thử nội bộ trước** (TestFlight / Google internal testing, máy chủ thử,
dữ liệu mẫu). Đây là hướng dẫn kỹ thuật, không phải tư vấn pháp lý.

## 0. App gồm những gì (đã có trong repo)

| Phần | Ở đâu | Ghi chú |
| --- | --- | --- |
| Giao diện | `apps/accountant-web/` | Cùng code với bản web; trong app không có nút demo, không có ô nhập API |
| Vỏ iOS / Android | `apps/mobile/ios`, `apps/mobile/android` | Capacitor 8.6, Android target SDK 36, iOS 15+ |
| Cấu hình app | `apps/mobile/capacitor.config.json` | `appId` **cz.vietbiz.app** (tạm — xem §2) |
| Gói web cho app | `npm run build:web` | Ghi `config.js` (API cố định, https), CSP chặt, `viewport-fit=cover` |
| Icon, màn hình chờ | `npm run assets` | Vẽ từ chữ "V" của VietBiz, xuất mọi kích thước iOS/Android |
| Đăng nhập | `login.js`, `runtime.js` | OIDC + PKCE, mở **trình duyệt hệ thống** (RFC 8252), quay về `cz.vietbiz.app:/oauth/callback`; token chỉ giữ trong bộ nhớ |
| Kiểm tra tự động | `.github/workflows/mobile.yml` | Android: build APK debug mỗi PR; iOS: build simulator khi bấm chạy tay |

## 1. Việc chỉ anh làm được (thứ tự nên làm)

1. **Quyết định tên pháp lý đăng ký**: cá nhân hay công ty. Đăng ký dưới tên công ty cần số
   **D-U-N-S** (miễn phí, xin qua Apple/Dun & Bradstreet, mất vài ngày đến vài tuần).
   - Google Play: tài khoản **cá nhân** tạo sau 13.11.2023 phải chạy thử kín với **ít nhất 12
     người thử, liên tục 14 ngày** trước khi được lên production; tài khoản **tổ chức** thì
     không phải. → Nếu VietBiz có công ty, nên đăng ký Google Play dưới tên công ty.
2. **Apple Developer Program**: 99 USD/năm — developer.apple.com/programs.
3. **Google Play Console**: 25 USD một lần — play.google.com/console.
4. **Chọn `appId` cuối cùng** (vd. `cz.vietbiz.app` nếu anh giữ tên miền vietbiz.cz, hoặc theo
   tên miền thật của công ty). **Sau lần tải lên đầu tiên không đổi được.** Đổi ở
   `capacitor.config.json`, `android/app/build.gradle`, `strings.xml`, Xcode (Bundle Identifier),
   `Info.plist` (URL scheme) — báo Claude/Codex làm.
5. **Máy chủ thử có HTTPS** cho API (tạm thời, dữ liệu mẫu) — cần anh cho phép triển khai theo
   CLAUDE.md. Đặt: `VIETBIZ_AUTH_MODE=oidc`, các biến `VIETBIZ_OIDC_*`, và
   `VIETBIZ_CORS_ORIGINS=capacitor://localhost,https://localhost` (nguồn của web view iOS/Android).
6. **Máy chủ đăng nhập (OIDC) có email OTP** — xem §3.
7. **Một máy Mac có Xcode** (bản hiện hành) để ký và tải bản iOS lên; hoặc dịch vụ build đám mây
   (trả tiền — cần anh đồng ý).

## 2. Build trên máy

```bash
cd apps/mobile
npm ci
export VIETBIZ_API_URL=https://api-test.<tên-miền>      # API thử
export VIETBIZ_OIDC_ORIGIN=https://id.<tên-miền>        # máy chủ đăng nhập
npm run sync                     # build:web + cap sync
npx cap open android             # Android Studio → Run
npx cap open ios                 # Xcode (Mac) → chọn Team → Run
```

Kiểm tra nhanh: `npm test` (gói web có API https cố định, redirect của app, CSP).

## 3. Máy chủ đăng nhập: email + mã một lần

App dùng OIDC chuẩn, không gắn với nhà cung cấp nào. Yêu cầu với máy chủ đăng nhập:

- **Client công khai (public client), PKCE S256**, không client secret.
- **Redirect URI**: `cz.vietbiz.app:/oauth/callback` (app) và địa chỉ workspace web (nếu dùng).
- **CORS cho token endpoint**: cho phép `capacitor://localhost` và `https://localhost`.
- **Đăng nhập không mật khẩu bằng mã gửi qua email.**
  - **Zitadel** hỗ trợ email OTP sẵn; **Keycloak** thì không có sẵn, cần thêm extension
    (vd. *keycloak-2fa-email-authenticator*). → Đề xuất Zitadel tự chạy ở EU (phần mềm miễn
    phí; máy chủ thì tốn tiền — cần anh đồng ý).
- **Gửi email**: cần dịch vụ SMTP (quyết định E trước đó: dịch vụ email trả tiền để sau — với
  thử nội bộ có thể dùng SMTP của tên miền công ty).
- **Lưu ý MFA**: API mặc định đòi đăng nhập 2 lớp (`VIETBIZ_OIDC_REQUIRE_MFA=1`). Chỉ mã email
  là **một** lớp. Hai cách: (a) giữ MFA, máy chủ đăng nhập thêm passkey/ứng dụng mã; (b) anh
  quyết định tắt cho giai đoạn thử (`VIETBIZ_OIDC_REQUIRE_MFA=0`). **Đây là quyết định của anh.**

## 4. Thử nội bộ

**Android — Internal testing** (không cần duyệt, tối đa 100 người thử):
1. Tạo **upload key** một lần, cất ngoài repo (mất key = phải xin Google đổi):
   `keytool -genkeypair -v -keystore vietbiz-upload.jks -alias upload -keyalg RSA -keysize 4096 -validity 10000`
2. Tạo `apps/mobile/android/keystore.properties` (đã nằm trong `.gitignore`):
   `storeFile=/đường/dẫn/vietbiz-upload.jks`, `storePassword=…`, `keyAlias=upload`, `keyPassword=…`
3. `VIETBIZ_VERSION_CODE=1 npm run android:release` → `android/app/build/outputs/bundle/release/app-release.aab`
4. Play Console → tạo app → bật **Play App Signing** → Testing → Internal testing → tải `.aab`,
   thêm email người thử.

**iOS — TestFlight** (cần Mac):
1. App Store Connect → My Apps → **+** → Bundle ID `cz.vietbiz.app`.
2. `npm run sync && npx cap open ios` → Signing & Capabilities → chọn Team (ký tự động).
3. Product → Archive → Distribute App → App Store Connect → Upload.
4. TestFlight → Internal Testing → thêm người thử (tối đa 100, không cần duyệt).

Mỗi lần tải lên: tăng `VIETBIZ_VERSION_CODE` (Android) / Build (iOS).

## 5. Trước khi phát hành công khai — còn thiếu

| # | Việc | Vì sao | Ai |
| --- | --- | --- | --- |
| P0 | **Xoá tài khoản ngay trong app** (và một trang web để yêu cầu xoá) | Apple và Google đều đòi với app có tạo tài khoản | Claude/Codex + quyết định thời hạn lưu theo luật kế toán (GDPR_DRAFTS §3) |
| P0 | **Chính sách quyền riêng tư** ở một URL công khai (VI/CS/EN) | Bắt buộc ở cả hai cửa hàng | Luật sư duyệt bản nháp `docs/legal/GDPR_DRAFTS.md` |
| P0 | **Máy chủ production ở EU**, DPA, sao lưu | Dữ liệu kế toán thật | Anh quyết định (dịch vụ trả tiền) |
| P0 | Bỏ dải "bản thử / dữ liệu mẫu" khi chạy production | Hiện luôn hiện | Claude/Codex khi có máy chủ thật |
| P1 | **Giao diện điện thoại theo thiết kế** (OwnerHome, chụp hoá đơn, thu chi, ca) | Hiện dùng giao diện workspace co lại; Apple có thể từ chối app chỉ "bọc web" (Guideline 4.2) | Claude — bước tiếp theo |
| P1 | Chụp hoá đơn bằng camera trên Android | iOS mở camera từ ô chọn file; Android cần thử trên máy thật | Kiểm tra trên thiết bị |
| P1 | Giữ đăng nhập lâu hơn (refresh token trong Keychain/Keystore) | Hiện mở lại app phải đăng nhập lại (thường một chạm nhờ phiên của trình duyệt) | Sau khi chọn máy chủ đăng nhập |
| P2 | Ảnh chụp màn hình cửa hàng, video | Bắt buộc khi gửi duyệt | Chụp từ bản TestFlight/internal |

## 6. Khai báo quyền riêng tư (bản nháp — kiểm tra khi điền)

App Store "App Privacy" và Google Play "Data safety", theo những gì app làm hôm nay:

| Dữ liệu | Thu? | Mục đích | Gắn với người dùng | Theo dõi quảng cáo |
| --- | --- | --- | --- | --- |
| Email (đăng nhập) | Có | Chức năng app, tài khoản | Có | Không |
| Tên hiển thị | Có | Chức năng app | Có | Không |
| Ảnh/tệp hoá đơn | Có (khi người dùng tải lên) | Chức năng app (kế toán) | Có | Không |
| Thông tin tài chính (hoá đơn, sao kê, thu chi) | Có | Chức năng app | Có | Không |
| Vị trí, danh bạ, quảng cáo, phân tích | **Không** | — | — | — |

- Mã hoá khi truyền: có (HTTPS). File gốc mã hoá khi lưu (AES-256-GCM, `docs/SECURITY_HARDENING.md`).
- Người dùng yêu cầu xoá được: **chưa** (P0 ở §5).
- `ITSAppUsesNonExemptEncryption = false`: app chỉ dùng HTTPS của hệ điều hành.
- Phân loại tuổi: không có nội dung nhạy cảm → mức thấp nhất; danh mục: **Kinh doanh / Tài chính**.

Nội dung trang cửa hàng (VI/CS/EN): `docs/mobile/STORE_LISTING.md`.
