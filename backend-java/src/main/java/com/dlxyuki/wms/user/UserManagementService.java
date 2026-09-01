package com.dlxyuki.wms.user;
import com.dlxyuki.wms.auth.AuthService;
import com.dlxyuki.wms.config.ApiException;
import java.util.*;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
@Service
public class UserManagementService {
    private static final Set<String> ROLES=Set.of("ADMIN","MANAGER","INBOUND","OUTBOUND","WAREHOUSE","VIEWER"), MODES=Set.of("ALL","SELECTED");
    private final UserRepository users; private final AuthService auth;
    public UserManagementService(UserRepository users,AuthService auth){this.users=users;this.auth=auth;}
    public List<UserResponse> list(UserAccount actor){admin(actor);return users.findAll().stream().map(UserResponse::from).toList();}
    public UserResponse bootstrap(UserRequests.Create p){if(users.count()!=0)throw new ApiException(HttpStatus.CONFLICT,"Bootstrap is already complete");return createInternal(p,"ADMIN");}
    public UserResponse create(UserRequests.Create p,UserAccount actor){admin(actor);String r=p.role()==null?"VIEWER":p.role(),w=p.warehouseScopeMode()==null?"ALL":p.warehouseScopeMode(),c=p.customerScopeMode()==null?"ALL":p.customerScopeMode();validate(r,w,c);List<Long> wi=list(p.warehouseIds()),ci=list(p.customerIds());validScopes(wi,ci);if(users.existsByUsernameOrEmail(p.username(),p.email()))throw new ApiException(HttpStatus.CONFLICT,"Username or email already exists");return UserResponse.from(users.create(p.username(),p.displayName(),p.email(),auth.hashPassword(p.password()),r,w,c,wi,ci));}
    private UserResponse createInternal(UserRequests.Create p,String forcedRole){String w=p.warehouseScopeMode()==null?"ALL":p.warehouseScopeMode(),c=p.customerScopeMode()==null?"ALL":p.customerScopeMode();validate(forcedRole,w,c);List<Long> wi=list(p.warehouseIds()),ci=list(p.customerIds());validScopes(wi,ci);if(users.existsByUsernameOrEmail(p.username(),p.email()))throw new ApiException(HttpStatus.CONFLICT,"Username or email already exists");return UserResponse.from(users.create(p.username(),p.displayName(),p.email(),auth.hashPassword(p.password()),forcedRole,w,c,wi,ci));}
    public UserResponse update(long id,UserRequests.Update p,UserAccount actor){admin(actor);if(users.findById(id).isEmpty())throw new ApiException(HttpStatus.NOT_FOUND,"User not found");if(p.role()!=null&&!ROLES.contains(p.role()))invalid();if(id==actor.id()&&p.role()!=null&&!"ADMIN".equals(p.role()))throw new ApiException(HttpStatus.UNPROCESSABLE_ENTITY,"Cannot remove your own admin role");if(id==actor.id()&&Boolean.FALSE.equals(p.isActive()))throw new ApiException(HttpStatus.UNPROCESSABLE_ENTITY,"Cannot deactivate your own account");return UserResponse.from(users.update(id,p.displayName(),p.email(),p.password()==null?null:auth.hashPassword(p.password()),p.role(),p.isActive()));}
    public UserResponse scope(long id,UserRequests.Scope p,UserAccount actor){admin(actor);if(users.findById(id).isEmpty())throw new ApiException(HttpStatus.NOT_FOUND,"User not found");validate("VIEWER",p.warehouseScopeMode(),p.customerScopeMode());List<Long> wi=list(p.warehouseIds()),ci=list(p.customerIds());validScopes(wi,ci);return UserResponse.from(users.updateScope(id,p.warehouseScopeMode(),p.customerScopeMode(),wi,ci));}
    private void validScopes(List<Long>w,List<Long>c){if(!users.scopesExist(w,c))throw new ApiException(HttpStatus.UNPROCESSABLE_ENTITY,"Unknown warehouse or customer scope id");}
    private static List<Long> list(List<Long>x){return x==null?List.of():x;}
    private static void validate(String r,String w,String c){if(!ROLES.contains(r)||!MODES.contains(w)||!MODES.contains(c))invalid();}
    private static void invalid(){throw new ApiException(HttpStatus.UNPROCESSABLE_ENTITY,"Invalid role or scope mode");}
    public static void admin(UserAccount a){if(!"ADMIN".equals(a.role()))throw new ApiException(HttpStatus.FORBIDDEN,"Admin permission required");}
}
