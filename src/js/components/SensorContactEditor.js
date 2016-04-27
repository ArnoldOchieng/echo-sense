'use strict';

var React = require('react');
var mui = require('material-ui'),
  RaisedButton = mui.RaisedButton,
  FlatButton = mui.FlatButton,

  Paper = mui.Paper,
  Dialog = mui.Dialog,
  TextField = mui.TextField;

var util = require('utils/util');
var toastr = require('toastr');
var api = require('utils/api');
var FetchedList = require('components/FetchedList');
var bootstrap = require('bootstrap');
var UserActions = require('actions/UserActions');
var UserStore = require('stores/UserStore');
import connectToStores from 'alt/utils/connectToStores';
import {changeHandler} from 'utils/component-utils';

@connectToStores
@changeHandler
export default class SensorContactEditor extends React.Component {
  static defaultProps = {
    contacts: {}
  }
  constructor(props) {
    super(props);
    this.state = {
      editing: false,
      form: {
        original_role: "",
        role: "",
        uid: null
      }
    };
  }
  static getStores() {
    return [UserStore];
  }
  static getPropsFromStores() {
    return UserStore.getState();
  }

  toggle_editing(editing) {
    this.setState({editing: editing});
  }

  edit_contact(role, uid) {
    this.setState({
      editing: true,
      form: {
        original_role: role,
        role: role,
        uid: uid
      }
    })
  }

  select_user(u) {
    var that = this;
    var contacts = this.props.contacts;
    var form = this.state.form;
    if (form.role.length > 0) {
      delete contacts[form.original_role];
      var uid = u != null ? u.id : form.uid;
      contacts[form.role] = uid;
      this.setState({editing: false}, function() {
        that.props.onChange(contacts);
      })
    }
  }

  render_user(u) {
    var label = u.name || u.phone || u.email;
    var selected_uid = this.state.form.uid == u.id;
    var cls = selected_uid ? "list-group-item-info" : "";
    return (<li key={u.id} className={"list-group-item " + cls}>
        <a href="javascript:void(0)" onClick={this.select_user.bind(this, u)} className="title">{ label }</a>
        <span className="sub">{ u.id }</span>
      </li>
    );
  }

  render() {
    var list = [];
    var form = this.state.form;
    var contacts = this.props.contacts;
    for (var contact_role in contacts) {
      if (contacts.hasOwnProperty(contact_role)) {
        var user_id = contacts[contact_role];
        var u = UserStore.get_user(user_id);
        var user_label = (u!=null) ? (u.name || u.email) : user_id;
        list.push(
          <li className="list-group-item">
            <a href="javascript:void(0)" className="title" onClick={this.edit_contact.bind(this, contact_role, user_id)}>{ contact_role }</a>
            <span className="right">{ user_label }</span>
          </li>
        );
      }
    }
    return (
        <div>
          <ul className="list-group">
          { list }
          </ul>

          <Dialog open={this.state.editing} onRequestClose={this.toggle_editing.bind(this, false)} actions={[<FlatButton label="Done" onClick={this.select_user.bind(this, null)} />]}>
            <TextField floatingLabelText="ID / Role" hint="No spaces, lower case" value={form.role} onChange={this.changeHandler.bind(this, 'form', 'role')} fullWidth={true} />

            <h3>Users</h3>
            <FetchedList url="/api/user" renderItem={this.render_user.bind(this)} autofetch={true} listProp="users" />

          </Dialog>
        </div>

    )
  }
}